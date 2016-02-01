# coding: utf-8
import pymongo
import os
import requests
import time
import datetime

conn = pymongo.Connection(os.environ['OPENSHIFT_MONGODB_DB_URL'])
db = conn.cptm

while True:
    req = requests.get('http://cptm.sp.gov.br/Pages/Home.aspx')
    db.requests.insert({
        'status_code': req.status_code,
        'content': req.content,
        'datetime': datetime.datetime.now()
    })
    time.sleep(30)
