# coding: utf-8
import os
import asyncio
import time
import requests
import datetime
import subprocess
import json
from jinja2 import Template
from bs4 import BeautifulSoup
from settings import db, base_path


@asyncio.coroutine
def get_requests(loop):
    """
    This will do requests from the CPTM website
    """
    while True:
        start_request = time.time()
        future = loop.run_in_executor(
            None,
            requests.get,
            'http://cptm.sp.gov.br/'
        )
        response = yield from future

        request_time = time.time() - start_request
        to_save = {
            'content': response.content,
            'status_code': response.status_code,
            'response_datetime': datetime.datetime.now(),
            'request_time': request_time
        }
        yield from loop.run_in_executor(
            None,
            db.requests.insert,
            to_save
        )

        print('[Request]: Returned {} status in {} seconds'.format(
            response.status_code, request_time
        ))
        yield from asyncio.sleep(10)


def pop_request():
    return db.requests.find_and_modify(remove=True)


def get_problem_nature(info):
    if 'Serviços de Manutenção' in info:
        return 'maintenance'
    return 'other'


def get_status_line(soup, line):
    div_line = soup.findAll('div', {'class': line})[0]
    span_info = div_line.findAll('span')[1]
    name = span_info['class'][0]
    data = {
        'name': name
    }
    try:
        info = span_info['data-original-title']
    except KeyError:
        pass
    else:
        data['info'] = info
        data['nature'] = get_problem_nature(info)

    return data


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
                start_process = time.time()

                soup_content = BeautifulSoup(request['content'], 'html.parser')
                status = {}
                all_normal = True

                try:
                    for line in lines:
                        status[line] = get_status_line(soup_content, line)
                        if status[line] != 'status_normal':
                            all_normal = False
                except IndexError:
                    request['error_date'] = datetime.datetime.now()
                    loop.run_in_executor(
                        None,
                        db.errors.insert,
                        request
                    )
                    print('[Process]: Error on process {}'.format(
                        request['_id']
                    ))
                else:
                    if all_normal:
                        del request['content']

                    request['status'] = status
                    request['process_time'] = time.time() - start_process

                    yield from loop.run_in_executor(
                        None, db.processed.save, request
                    )
                    print('[Process]: Processed  in {} seconds'.format(
                        request['process_time']
                    ))
        else:
            yield from asyncio.sleep(0.1)


def get_revision():
    JSON_GIT_FORMAT = ('{"hash": "%H", "author": "%an", "subject": "%s", '
                       '"date": "%ar"}')
    process = subprocess.Popen(['git', 'show', '--pretty=format:{}'.format(
        JSON_GIT_FORMAT
    )], stdout=subprocess.PIPE)
    out, err = process.communicate()
    out = out.decode().split('\n')[0]
    data = json.loads(out)
    return data


@asyncio.coroutine
def generate_index(loop):
    while True:
        get_revision()
        print('[Template]: Start template generation')
        template_file = os.path.join(base_path, 'template.html')

        revision = yield from loop.run_in_executor(
            None,
            get_revision
        )

        try:
            template = open(template_file, encoding='utf-8').read()
        except IOError:
            print('[Template]: Error on open file')
        else:
            latest = yield from loop.run_in_executor(
                None,
                db.processed.find().sort([('_id', -1)]).limit,
                1
            )
            latest = latest[0]
            first = yield from loop.run_in_executor(
                None,
                db.processed.find().sort([('_id', 1)]).limit,
                1
            )
            first = first[0]

            non_processed = yield from loop.run_in_executor(
                None,
                db.requests.count
            )
            processed = yield from loop.run_in_executor(
                None,
                db.processed.count
            )
            errors = yield from loop.run_in_executor(
                None,
                db.errors.count
            )
            now = datetime.datetime.now()
            interval = now - datetime.timedelta(days=1)
            categories = []
            data = []
            data_errors = []
            data_total = []

            for i in range(1, 24):
                categories.append(interval.strftime('%d/%m/%Y %H:%M:%S'))
                end_interval = interval + datetime.timedelta(hours=1)

                interval_requests = yield from loop.run_in_executor(
                    None,
                    db.processed.find({
                        'response_datetime': {
                            '$gte': interval,
                            '$lt': end_interval
                        }
                    }).count
                )
                data.append(interval_requests)
                interval_errors = yield from loop.run_in_executor(
                    None,
                    db.errors.find({
                        'response_datetime': {
                            '$gte': interval,
                            '$lt': end_interval
                        }
                    }).count
                )
                data_errors.append(interval_errors)
                data_total.append(interval_errors + interval_requests)

                interval = end_interval

            latest['lines'] = latest['status'].items()
            context = {
                'latest': latest,
                'first': first,
                'non_processed': non_processed,
                'processed': processed,
                'errors': errors,
                'revision': revision,
                'responses_chart': {
                    'categories': categories,
                    'data': data,
                    'data_errors': data_errors,
                    'data_total': data_total
                }
            }
            index = Template(template).render(**context)
            index_file = os.path.join(base_path, 'index.html')

            try:
                open(index_file, 'w').write(index)
            except IOError:
                print('[Template]: Error on save the file')
            else:
                print('[Template]: End template generation')
        yield from asyncio.sleep(1)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    tasks = [
        process_requests(loop),
        get_requests(loop),
        generate_index(loop)
    ]
    loop.run_until_complete(asyncio.wait(tasks))
