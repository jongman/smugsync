#!/usr/bin/python
import os
import shelve
import smugmug
import smugsync
import sys
import logging
import utils
import traceback
import StringIO

assert len(sys.argv) == 4, "need to have (dir) (categoryname) (subcategoryname)"
directory, category, subcategory = sys.argv[1:]

api = smugmug.API()
api.login()

categories = api.get_categories()
category_id = categories[category]
subcategories = api.get_subcategories(category_id)
if subcategory not in subcategories:
    subcategory_id = api.create_subcategory(category_id, subcategory)
else:
    subcategory_id = subcategories[subcategory]

albums = dict((alb["Title"], alb["id"]) for alb in api.get_albums())
def get_album_id(name):
    if name not in albums:
        albums[name] = api.create_album(name, category_id,
                                        {"Public": False,
                                         "SmugSearchable": False,
                                         "SubCategoryID": subcategory_id})
        api.change_album_setting(albums[name], {"SortDirection": "false",
                                                "SortMethod":
                                                "DateTimeOriginal"})
    return albums[name]

uploaded = shelve.open("uploader.data")
def upload(path):
    if path in uploaded:
        #logging.info("%s already uploaded", path)
        return
    dir = os.path.relpath(os.path.dirname(path),
                          directory)
    album_name = dir.decode("euc-kr").replace("\\", "/").encode("utf-8")
    album_id = get_album_id(album_name)
    try:
        api.upload(path, album_id, hidden=True)
    except Exception as e:
        print "Exception: %s" % str(e)
        io = StringIO.StringIO()
        traceback.print_exc(file=io)
        io.seek(0)
        print "Stack trace:\n%s" % io.read()
        raise

    uploaded[path] = True
    uploaded.sync()

#utils.setup_logging("uploader.log", "mbcs")
#logging.info("Scanning..")
files = smugsync.scan_incoming([directory])
# for file in files:
#     file = file.decode("euc-kr")
#     print type(file), file
#     break
# files = []
#logging.info("Scanned %d jobs.", len(files))
for i, file in enumerate(files):
    #file = file.decode("euc-kr")
    print "uploading", i+1, "of", len(files)
    #logging.info("Uploading %d out of %d", i+1, len(files))
    upload(file)
