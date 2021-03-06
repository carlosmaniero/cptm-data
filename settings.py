# coding: utf-8
import pymongo
import os
import requests
import time
import datetime
import asyncio
import time
from jinja2 import Template
from bs4 import BeautifulSoup

url = os.environ.get('OPENSHIFT_MONGODB_DB_URL')
debug = os.environ.get('DEBUG_MODE', False)
conn = pymongo.Connection(url)
db = conn.cptm
base_path = os.path.dirname(__file__)
host = 'localhost'
port = 6447


def pop_request():
    return db.requests.find_and_modify(remove=True)


def get_status_line(soup, line):
    div_line = soup.findAll('div', {'class': line})[0]
    return div_line.findAll('span')[1]['class'][0]


@asyncio.coroutine
def get_requests(loop):
    """
    This will do requests from the CPTM website
    """
    while True:
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
        yield from asyncio.sleep(90)


@asyncio.coroutine
def process_requests(loop):
    lines = [
        'rubi', 'diamante', 'esmeralda', 'turquesa', 'coral', 'safira'
    ]

    while True:
        total_requests = yield from loop.run_in_executor(
            None,
            db.requests.find().count
        )
        print('[Process]: Total of non processed requests: {}'.format(
            total_requests
        ))
        if total_requests:
            request = yield from loop.run_in_executor(
                None, pop_request
            )

            # Another loop can get it before
            if request:
                print(request)
                start_process = time.time()

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

                yield from loop.run_in_executor(
                    None, db.requests.save, request
                )
                print('[Process]: Processed  in {} seconds'.format(
                    request['process_time']
                ))
        yield from asyncio.sleep(0.1)


@asyncio.coroutine
def generate_index(loop):
    while True:
        print('[Template]: Start template generation')
        template_file = os.path.join(BASE_PATH, 'template.html')
        template = open(template_file, encoding='utf-8').read()

        latest = yield from loop.run_in_executor(
            None,
            db.requests.find({'processed': True}).sort([('_id', -1)]).limit,
            1
        )
        latest = latest[0]

        total = yield from loop.run_in_executor(
            None,
            db.requests.count
        )
        processed = yield from loop.run_in_executor(
            None,
            db.requests.find(processed=True).count
        )
        context = {
            'latest': latest,
            'total': total,
            'processed': processed
        }
        index = Template(template).render(**context)
        index_file = os.path.join(BASE_PATH, 'index.html')
        open(index_file, 'w').write(index)
        print('[Template]: End template generation')
        yield from asyncio.sleep(10)


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
        generate_index(loop)
    ]
    if debug:
        tasks += [check_for_blocking()]
    loop.run_until_complete(asyncio.wait(tasks))
