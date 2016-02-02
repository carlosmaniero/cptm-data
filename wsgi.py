#!/usr/bin/env python
# coding: utf-8
import os
import pymongo

BASE_PATH = os.path.dirname(__file__)
index = open(os.path.join(BASE_PATH, 'index.html'), encoding='utf-8').read()

url = os.environ.get('OPENSHIFT_MONGODB_DB_URL')
debug = os.environ.get('DEBUG_MODE', False)
conn = pymongo.Connection(url)
db = conn.cptm

def application(environ, start_response):

    ctype = 'text/plain'
    if environ['PATH_INFO'] == '/health':
        response_body = "1"
    elif environ['PATH_INFO'] == '/env':
        response_body = ['%s: %s' % (key, value) for key, value in sorted(environ.items())]
        response_body = '\n'.join(response_body)
    else:
        ctype = 'text/html'
        response_body = index.format(
            total=db.requests.count(),
            processed=db.requests.find(processed=True).count()
        )
        response_body = response_body.encode('utf-8')

    status = '200 OK'
    response_headers = [('Content-Type', ctype), ('Content-Length', str(len(response_body)))]
    #
    start_response(status, response_headers)
    return [response_body ]

#
# Below for testing only
#
if __name__ == '__main__':
    from wsgiref.simple_server import make_server
    httpd = make_server('localhost', 8051, application)
    # Wait for a single request, serve it and quit.
    httpd.handle_request()
