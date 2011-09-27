#!/usr/bin/python
import os
import shelve
import smugmug
import smugsync
import sys
import logging
import utils

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
    if path in uploaded: return
    dir, filename = os.path.split(path)

    album_name = dir.replace("\\", "/")
    album_id = get_album_id(album_name)
    api.upload(path, album_id, hidden=True)

    uploaded[path] = True
    uploaded.sync()

utils.setup_logging("uploader.log")
logging.info("Scanning..")
files = smugsync.scan_incoming([directory])
logging.info("Scanned %d jobs.", len(files))
for i, file in enumerate(files):
    logging.info("Uploading %s (%d out of %d)", file, i+1, len(files))
    upload(file)
