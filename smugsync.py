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
import utils
import smugmug
import StringIO
import config
import logging
import json

PROJECT_PATH = os.path.dirname(__file__)
SHELF_PATH = os.path.join(PROJECT_PATH, "shelf.db")

global uploaded, copied

def open_shelf(filename):
    path = os.path.join(PROJECT_PATH, filename)
    return shelve.open(path)

def setup():
    global copied, uploaded, last_scanned, warnings
    copied = open_shelf("copied.db")
    uploaded = open_shelf("uploaded.db")
    last_scanned = []

    log_path = os.path.join(PROJECT_PATH, "smugsync.log")
    utils.setup_logging(log_path)
    warnings = StringIO.StringIO()
    handler = logging.StreamHandler(warnings)
    handler.setLevel(logging.WARNING)
    logging.getLogger("").addHandler(handler)


def get_extension(filename):
    return filename.split(".")[-1].lower()

def scan_incoming(read_from=None):
    read_from = read_from or config.READ_FROM
    extset = set([ext.lower() for ext in config.RECOGNIZED_EXTS])
    ret = []
    for incoming in read_from:
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
    global uploaded
    copy = []
    for path in files:
        try:
            filesize = get_file_size(path)
            # read a small portion of the whole file to generate unique id
            md5 = md5file(path, config.SIGNATURE_SIZE)
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
    if not config.SMTP_SERVER: return
    server = smtplib.SMTP(config.SMTP_SERVER)
    server.starttls()
    server.login(config.SMTP_ID, config.SMTP_PASSWORD)
    server.sendmail(config.FROM_EMAIL, config.TO_EMAIL, msg)
    server.quit()

def notify_warnings(warnings):
    notify("SmugSync: %d warnings" % (len(warnings.split("\n"))),
           "Hello! I got some warnings from last iterations. Prolly some "
           "duplicate files. See for yourself:\n%s" % warnings)

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

def notify_upload_start(jobcount):
    logging.info("Notifying upload start of %d files.", jobcount)
    notify("SmugSync: Uploading Started (%d files)" % jobcount,
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
    logging.info("get_digits(%s) = %d", fn, ret)
    return ret

def compare_file_no(a, b):
    diff = get_digits(a["filename"]) - get_digits(b["filename"])
    if diff > 0: return 1
    if diff < 0: return -1
    return 0

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
        if dates[i]: curdate = dates[i]
        if dates[i] is None: dates[i] = curdate
    curdate = None
    for i in xrange(len(jobs)-1, -1, -1):
        if dates[i]: curdate = dates[i]
        if dates[i] is None: dates[i] = curdate
    for i in xrange(len(jobs)):
        if dates[i] is None:
            dates[i] = detect_mod_date(job["origin"])
        jobs[i]["date"] = dates[i]

def perform_copy_job(job):
    target_dir = os.path.join(config.WRITE_TO, job["date"])
    try:
        os.makedirs(target_dir)
    except OSError:
        pass
    target_path = os.path.join(target_dir, job["filename"])
    if os.path.exists(target_path):
        logging.warning("target_path already exists: origin %s target_path %s",
                        job["origin"],
                        target_path)
        return

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
    # print json.dumps(jobs, indent=4)

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
    album_name = config.ALBUM_FORMAT.format(date=job["date"])
    if album_name not in albums:
        subcategory_name = "-".join(job["date"].split("-")[:2])
        subcategory_id = get_subcategory_id(subcategory_name)
        albums[album_name] = api.create_album(album_name, category_id,
                {"Public": not config.HIDDEN_GALLERIES,
                 "SmugSearchable": not config.HIDDEN_GALLERIES,
                 "SubCategoryID": subcategory_id})
        api.change_album_setting(albums[album_name],
                                 {"SortDirection": "false",
                                  "SortMethod": "DateTimeOriginal"})
    return albums[album_name]

def upload_all():
    # temporary: filter out large files. I should figure out how to upload the
    # large ones.
    jobs = [(val["dest"], key) for key, val in copied.iteritems()
            if val["filesize"] <= config.MAX_FILE_SIZE]
    if not jobs: return
    notify_upload_start(len(jobs))
    global api

    api = smugmug.API()
    api.login()

    global albums, category_id, subcategories
    albums = dict((alb["Title"], alb["id"]) for alb in api.get_albums())
    categories = api.get_categories()
    category_id = categories[config.DEFAULT_CATEGORY]
    subcategories = api.get_subcategories(category_id)
    done, cnt = 0, len(copied)
    try:
        jobs.sort()
        jobs.reverse()
        for _, key in jobs:
            job = copied[key]
            album_id = get_album_id(job)
            api.upload(job["dest"], album_id, hidden=config.HIDDEN_PICTURES)
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
    global warnings
    while True:

        warnings.seek(0)
        warnings.truncate(0)

        logging.info("Started checking!")
        scanned = scan_incoming()
        if not is_something_new(scanned):
            logging.info("Apparently nothing is new.")
        else:
            copy_all(scanned)
        try:
            upload_all()
        except smugmug.SmugmugException as e:
            logging.error("Smugmug gave us an exception. Response: %s.",
                    e.response)
            logging.error("Stack trace:\n%s", utils.print_stack_trace())
        logging.info("We are done. :-)")

        warnings.seek(0)
        warnings_logged = warnings.read()
        if warnings_logged:
            logging.info("There were some warnings logged. Notifying.")
            notify_warnings(warnings_logged)

        if "--repeat" not in sys.argv:
            break
        reload(config)
        time.sleep(config.CHECK_INTERVAL)

def main():
    try:
        setup()
        process()
    except Exception as e:
        logging.error("Uncaught exception. Message: %s. How sad.", str(e))
        logging.error("Stack trace:\n%s", utils.print_stack_trace())

if __name__ == "__main__":
    main()
