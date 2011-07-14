#!/usr/bin/python
# -*- coding: utf-8 -*-

import time
import traceback
import datetime
import minimal_exif_reader
import hashlib
import os
import shelve
import shutil
import smtplib
import sys
from config import *
import utils
import smugmug
import StringIO

PROJECT_PATH = os.path.dirname(__file__)
SHELF_PATH = os.path.join(PROJECT_PATH, "shelf.db")

def open_shelf(filename):
    path = os.path.join(PROJECT_PATH, filename)
    return shelve.open(path)

def setup():
    global copied, uploaded, last_scanned
    copied = open_shelf("copied.db")
    uploaded = open_shelf("uploaded.db")
    last_scanned = []

    log_path = os.path.join(PROJECT_PATH, "smugsync.log")
    utils.setup_logging(log_path)

def get_extension(filename):
    return filename.split(".")[-1].lower()

def scan_incoming():
    extset = set([ext.lower() for ext in RECOGNIZED_EXTS])
    ret = []
    for incoming in READ_FROM:
        try:
            for path, __, files in os.walk(incoming):
                ret += [os.path.join(path, file) for file in files
                        if get_extension(file) in extset]
        except Exception as e:
            logging.error("scan_incoming got an exception while scanning"
                    "%s.\nException message: %s\nNo biggie, will try later "
                    "again.", incoming, str(e))
            return []
    logging.info("Recognized %d scanned.", len(ret))
    return sorted(ret)

def md5file(file_path, max_len=None):
    if max_len is None: max_len = get_file_size(file_path)
    md5 = hashlib.md5()
    CHUNK = 1024*1024*4
    fp = open(file_path, "rb")
    while max_len > 0:
        rd = min(max_len, CHUNK)
        md5.update(fp.read(rd))
        max_len -= rd

    return md5.hexdigest()

def get_copy_jobs(files):
    copy = []
    for path in files:
        try:
            filesize = get_file_size(path)
            # read a small portion of the whole file to generate unique id
            md5 = md5file(path, SIGNATURE_SIZE)
            key = "|".join([str(filesize), md5])
            if key in copied or key in uploaded: continue
            logging.info("Recognized key %s. Adding to copy queue.", key)
            filename = os.path.basename(path)
            copy.append({"key": key, "origin": path, "filename": filename,
                "filesize": filesize, "md5": md5file(path)})
        except Exception as e:
            logging.error("get_copy_jobs got an error while copying %s.\n"
                    "Exception message: %s\nNo biggie, will try later "
                    "again.", path, str(e))

    return copy

def notify(subject, msg):
    msg = "Subject: %s\n\n%s" % (subject, msg)
    logging.info("Sending notification:\n%s", msg)
    if not SMTP_SERVER: return
    server = smtplib.SMTP(SMTP_SERVER)
    server.starttls()
    server.login(SMTP_ID, SMTP_PASSWORD)
    server.sendmail(FROM_EMAIL, TO_EMAIL, msg)
    server.quit()

def notify_copy_start():
    logging.info("Start scanning for copy jobs ..")
    notify("SmugSync: Copy Initiated",
        "Hello! Just so you know that I started scanning files from "
        "your SD card. So don't eject it alright?")

def notify_copy_finish(copied, failed):
    logging.info("Copy done.")
    message = "Hello! Copy has finished. Now you can eject your SD card."
    if failed:
        message += ("\nBy the way, some files we have failed to copy. "
                "Might be a couple reasons -- disk full is one comes to "
                "mind -- so check it out. List of failed files follows.\n"
                + "\n".join(failed))
    notify("SmugSync: Copy Finished (%d copied, %d failed)" % (copied,
        len(failed)), message)

def notify_upload_start(jobs):
    logging.info("Notifying upload start of %d files.", len(jobs))
    notify("SmugSync: Uploading Started (%d files)" % len(jobs),
            "Hello! Just so you know I started uploading files from "
            "your hard drive. I'll let you know once it gets finished.")

def notify_upload_finish(done):
    logging.info("Notifying upload finish of %d files.", done)
    notify("SmugSync: Upload Finished", 
            "Hello! Upload is finished so you'll be able to see your files "
            "soon.")

def notify_upload_fail(uploaded):
    notify("SmugSync: Upload Failed (after %d files)" % uploaded, 
            "Hello! Sorry but loads failed. Maybe something is wrong. "
            "I will automatically retry later, so no worries.")

def get_digits(fn):
    ret = 0
    for ch in fn:
        if ch.isdigit():
            ret = ret * 10 + int(ch)
    return ret

def compare_file_no(a, b):
    return get_digits(a["filename"]) - get_digits(b["filename"])

def get_jpg_date(path):
    try:
        dt = minimal_exif_reader.MinimalExifReader(path).dateTimeOriginal()
        assert dt
        return "-".join(dt.split()[0].split(":"))
    except:
        return None

def get_file_size(path):
    return os.stat(path).st_size

def detect_mod_date(path):
    stat = os.stat(path)
    return datetime.date.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")

def detect_dates(jobs):
    jobs.sort(cmp=compare_file_no)
    dates = [None] * len(jobs)
    for i, job in enumerate(jobs):
        if get_extension(job["filename"]) == "jpg":
            dates[i] = get_jpg_date(job["origin"])
    curdate = None
    # for undetermined dates, populate by looking at other files
    for i in xrange(len(jobs)):
        curdate = curdate or dates[i]
        if dates[i] is None:
            dates[i] = curdate
    curdate = None
    for i in xrange(len(jobs)-1, -1, -1):
        curdate = curdate or dates[i]
        if dates[i] is None:
            dates[i] = curdate
    for i in xrange(len(jobs)):
        if dates[i] is None:
            dates[i] = detect_mod_date(job["origin"])
        jobs[i]["date"] = dates[i]

def perform_copy_job(job):
    target_dir = os.path.join(WRITE_TO, job["date"])
    try:
        os.makedirs(target_dir)
    except OSError:
        pass
    target_path = os.path.join(target_dir, job["filename"])
    job["dest"] = target_path
    retries = 0
    while retries < 3:
        retries += 1
        try:
            shutil.copy(job["origin"], job["dest"])
        except:
            logging.error("Somehow we got an exception during copy.")
            logging.error("Origin [%s] dest [%s]", job["origin"],
                    job["dest"])
            continue
        copied_md5 = md5file(job["dest"])
        if copied_md5 != job["md5"]:
            logging.info("MD5 does not match for origin %s",
                    job["origin"])
            logging.info("Expected: %s Got: %s", job["md5"], copied_md5)
            continue
        break
    # try it at a later date :-(
    if retries == 3:
        return
    copied[job["key"]] = job
    copied.sync()

def perform_copy(jobs):
    detect_dates(jobs)
    copied, failed = 0, []
    for i, job in enumerate(jobs):
        try:
            perform_copy_job(job)
            logging.info("Imported %s (that's %d of %d)", job["origin"], i+1,
                    len(jobs))
            copied += 1
        except:
            logging.info("Failed to copy %s.", job["origin"])
            failed.append(job["origin"])
    return copied, failed

def copy_all(scanned):
    notify_copy_start()
    copy_jobs = get_copy_jobs(scanned)
    if not copy_jobs:
        logging.info("There were no new files.")
        copied, failed = 0, []
    else:
        copied, failed = perform_copy(copy_jobs)
    notify_copy_finish(copied, failed)

def head(dic):
    key = dic.iterkeys().next()
    return key, dic[key]

def get_subcategory_id(subcategory_name):
    if subcategory_name not in subcategories:
        subcategories[subcategory_name] = api.create_subcategory(category_id,
                subcategory_name)
    return subcategories[subcategory_name] 

def get_album_id(job):
    album_name = ALBUM_FORMAT.format(date=job["date"])
    if album_name not in albums:
        subcategory_name = "-".join(job["date"].split("-")[:2])
        subcategory_id = get_subcategory_id(subcategory_name)
        albums[album_name] = api.create_album(album_name, category_id,
                {"Public": not HIDDEN_GALLERIES,
                 "SmugSearchable": not HIDDEN_GALLERIES,
                 "SubCategoryID": subcategory_id})
    return albums[album_name]

def upload_all():
    if not copied: return
    notify_upload_start(copied.values())
    global api

    api = smugmug.API()
    api.login()

    global albums, category_id, subcategories
    albums = dict((alb["Title"], alb["id"]) for alb in api.get_albums())
    categories = api.get_categories()
    category_id = categories[DEFAULT_CATEGORY]
    subcategories = api.get_subcategories(category_id)
    done, cnt = 0, len(copied)
    try:
        jobs = [(val["dest"], key) for key, val in copied.iteritems()]
        jobs.sort()
        jobs.reverse()
        for _, key in jobs:
            job = copied[key]
            # ignore large files for now: need some other way to upload things
            if job["filesize"] >= MAX_FILE_SIZE: continue
            album_id = get_album_id(job)
            api.upload(job["dest"], album_id, 
                    {"X-Smug-Hidden": HIDDEN_PICTURES})
            del copied[key]
            copied.sync()
            uploaded[key] = job
            uploaded.sync()
            done += 1
            logging.info("Uploaded %s. That's %d out of %d.", job["dest"], 
                    done, cnt)
        notify_upload_finish(done)
    except Exception as e:
        logging.error("Exception: %s", str(e))
        io = StringIO.StringIO()
        traceback.print_exc(file=io)
        io.seek(0)
        logging.error("Stack trace:\n%s", io.read())
        notify_upload_fail(done)
        logging.info("Upload failed after %d uploads. Maybe some other day.",
            done)

def is_something_new(scanned):
    global last_scanned
    ret = scanned and last_scanned != scanned
    last_scanned = scanned
    return ret

def process():
    while True:
        logging.info("Started checking!")
        scanned = scan_incoming()
        if not is_something_new(scanned):
            logging.info("Apparently nothing is new.")
        else:
            copy_all(scanned)
            upload_all()
            logging.info("We are done. :-)")
        if "--repeat" not in sys.argv:
            break
        time.sleep(CHECK_INTERVAL)

def main():
    try:
        setup()
        process()
    except Exception as e:
        logging.error("Uncaught exception. Message: %s. How sad.", str(e))
        io = StringIO.StringIO()
        traceback.print_exc(file=io)
        io.seek(0)
        logging.error("Stack trace:\n%s", io.read())

if __name__ == "__main__":
    main()
