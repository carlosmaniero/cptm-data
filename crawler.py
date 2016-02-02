# coding: utf-8
import pymongo
import os
import requests
import time
import datetime
import asyncio
import time
from bs4 import BeautifulSoup

url = os.environ.get('OPENSHIFT_MONGODB_DB_URL')
debug = os.environ.get('DEBUG_MODE', False)
conn = pymongo.Connection(url)
db = conn.cptm


def find_one_request(processed=False, processing=False):
    return db.requests.find_one({
        'processed': processed,
        'status_code': 200,
        'processing': {
            '$ne': not processing
        }
    })


def get_status_line(soup, line):
    return soup.findAll('div', {'class': 'rubi'})[0].findAll('span')[1]['class'][0]


@asyncio.coroutine
def get_requests(loop):
    """
    This will do requests from the CPTM website
    """
    while True:
        try:
            start_request = time.time()
            future_response = loop.run_in_executor(
                None,
                requests.get,
                'http://cptm.sp.gov.br/'
            )
            response = yield from future_response

            request_time = time.time() - start_request
            to_save = {
                'content': response.content,
                'status_code': response.status_code,
                'response_datetime': datetime.datetime.now(),
                'processed': False,
                'request_time': request_time
            }
            data = yield from loop.run_in_executor(
                None,
                db.requests.insert,
                to_save
            )
            print('[Request]: Returned {} status in {} seconds'.format(
                response.status_code, request_time
            ))
        except:
            # TODO: Put log here
            pass
        yield from asyncio.sleep(10)


@asyncio.coroutine
def process_requests(loop):
    lines = [
        'rubi', 'diamante', 'esmeralda', 'turquesa', 'coral', 'safira'
    ]

    while True:
        total_requests = yield from loop.run_in_executor(
            None,
            db.requests.find({'processed': False}).count
        )
        print('[Process]: Total of non processed requests: {}'.format(
            total_requests
        ))
        if total_requests:
            request = yield from loop.run_in_executor(
                None, find_one_request
            )

            # Another loop can get it before
            if request:
                start_process = time.time()

                # Block from another process
                request['processing'] = True
                yield from loop.run_in_executor(
                    None, db.requests.save, request
                )
                soup_content = BeautifulSoup(request['content'], 'html.parser')
                status = {}
                all_normal = True

                for line in lines:
                    status[line] = get_status_line(soup_content, line)
                    if status[line] != 'status_normal':
                        all_normal = False

                if all_normal:
                    del request['content']

                request['status'] = status
                request['process_time'] = time.time() - start_process
                request['processing'] = False
                request['processed'] = True

                yield from loop.run_in_executor(
                    None, db.requests.save, request
                )
                print('[Process]: Processed  in {} seconds'.format(
                    request['process_time']
                ))
        yield from asyncio.sleep(0.1)


@asyncio.coroutine
def check_for_blocking():
    while True:
        print('[RUN]: OK')
        yield from asyncio.sleep(0.5)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    tasks = [
        get_requests(loop),
        process_requests(loop),
    ]
    if debug:
        tasks += [check_for_blocking()]
    loop.run_until_complete(asyncio.wait(tasks))
