#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import logging.handlers
import hashlib
import os
import shelve
import sys
from config import *

PROJECT_PATH = os.path.dirname(__file__)
SHELF_PATH = os.path.join(PROJECT_PATH, "shelf.db")

def setup():
    global shelf
    shelf = shelve.open(SHELF_PATH)

    logger = logging.getLogger("")
    logger.setLevel(LOGGING_LEVEL)

    log_path = os.path.join(PROJECT_PATH, "smugsync.log")

    formatter = logging.Formatter(fmt="%(asctime)-15s %(levelname)s %(message)s")
    handler = logging.handlers.RotatingFileHandler(log_path,
            maxBytes=1024*1024, backupCount=3)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)

def scan_incoming():
    extset = set([ext.lower() for ext in RECOGNIZED_EXTS])
    ret = []
    for incoming in READ_FROM:
        for path, __, files in os.walk(incoming):
            ret += [os.path.join(path, file) for file in files 
                    if file.split(".")[-1].lower() in extset]
    return sorted(ret)

def is_file_list_changed(files):
    key = "LastRunFileList"
    if key not in shelf or shelf[key] != files:
        shelf[key] = files
        return True
    return False

def md5file(file_path):
    md5 = hashlib.md5()
    md5.update(open(file_path, "rb").read())
    return md5.hexdigest()

def get_shelf_key(path):
    filename = os.path.basename(path)
    md5 = md5file(path)
    return "|".join([filename, md5])

def get_job_list(files):
    copy, upload = [], []
    for path in files:
        key = get_shelf_key(path)
        file_state = shelf.get(key, "none")
        if file_state == "none":
            copy.append(path)
        if file_state != "uploaded":
            upload.append(path)
    return copy, upload

def perform_copy(copy_jobs):
    pass

def perform_upload(upload_jobs):
    pass

def process():
    logging.info("Started checking!")

    files = scan_incoming()

    logging.info("Recognized %d files.", len(files))

    if not is_file_list_changed(files):
        logging.info("Seems like nothing is changed. Bah!")
        return

    copy_jobs, upload_jobs = get_job_list(files)

    logging.info("We have found %d copy jobs and %d upload jobs.",
            len(copy_jobs), len(upload_jobs))

    if copy_jobs: perform_copy(copy_jobs)
    if upload_jobs: perform_upload(upload_jobs)

    logging.info("We are done. :-)")

def main():
    setup()
    process()

if __name__ == "__main__":
    main()
