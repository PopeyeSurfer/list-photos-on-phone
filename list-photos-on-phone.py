#!/usr/bin/env python
# A command-line script for the Windows OS to find the photos that haven't been
# copied from a connected iPhone to the local machine yet.

import os
import sys
import time
from argparse import ArgumentParser
from win32com.shell import shell, shellcon
import pywintypes
from collections import defaultdict
import yaml

__author__ = "David Blume"
__copyright__ = "Copyright 2014, David Blume"
__license__ = "http://www.wtfpl.net/"


def set_v_print(verbose):
    """
    Defines the function v_print.
    It prints if verbose is true, otherwise, it does nothing.
    See: http://stackoverflow.com/questions/5980042
    :param verbose: A bool to determine if v_print will print its args.
    """
    global v_print
    if verbose:
        def v_print(*s):
            print " ".join(s)
    else:
        v_print = lambda *s: None


def process_photos(folder, photo_dict, prev_index):
    """
    Adds photos to photo_dict if they are newer than prev_index.
    :param folder: The PIDL of the folder to walk.
    :param photo_dict: A defaultdict of pathname to list of photos.
    :param prev_index: The index in the filename of the most recent photo
                       already copied to the local disk
    """
    for pidl in folder.EnumObjects(0, shellcon.SHCONTF_NONFOLDERS):
        name = folder.GetDisplayNameOf(pidl, shellcon.SHGDN_FORADDRESSBAR)
        dirname = os.path.dirname(name)
        basename, ext = os.path.splitext(os.path.basename(name))
        if ext.endswith("JPG"):
            # Failed Experiment 1: Get creation date
            # SHGetDataFromIDList() does not exist
            # data = shell.SHGetDataFromIDList(folder, pidl,
            #             shellcon.SHGDFIL_FINDDATA)

            # Failed Experiment 2: Get creation date
            # raises pywintypes.com_error: ('The parameter is incorrect.')
            # requires: from win32com.propsys import pscon
            # item = shell.SHCreateItemFromIDList(pidl, shell.IID_IShellItem2)
            # filetime = item.GetFileTime(pscon.PKEY_DateCreated)

            # Failed Experiment 3: Open file to stream
            # raises TypeError: The Python instance can not be a COM object
            # item = shell.SHCreateItemFromIDList(pidl, shell.IID_IShellItem2)
            # Note pythoncom.IID_IStream
            # stream = item.BindToHandler(0, shell.BHID_Stream, ???)

            # Experiment 4: List only the images that are newer.
            if index_from_filename(basename) > prev_index:
                photo_dict[dirname].append(name)


def walk_dcim_folder(dcim_pidl, parent, prev_index):
    """
    Iterates all the subfolders of the iPhone's DCIM directory, gathering
    photos that need to be processed in photo_dict.

    :param dcim_pidl: A PIDL for the iPhone's DCIM folder
    :param parent: The parent folder of the PIDL
    :param prev_index: The index in the filename of the most recent photo
                       already copied to the local disk
    """
    photo_dict = defaultdict(list)
    dcim_folder = parent.BindToObject(dcim_pidl, None, shell.IID_IShellFolder)
    for pidl in dcim_folder.EnumObjects(0, shellcon.SHCONTF_FOLDERS):
        folder = dcim_folder.BindToObject(pidl, None, shell.IID_IShellFolder)
        process_photos(folder, photo_dict, prev_index)

    for key in photo_dict:
        for item in sorted(photo_dict[key]):
            print item
        print


def get_dcim_folder(device_pidl, parent):
    """
    Tries to find an iPhone by searching the pidl for the path
    "Internal Storage\DCIM".
    :param device_pidl: A candidate Windows PIDL for the iPhone
    :param parent: The parent folder of the PIDL
    """
    device_name = parent.GetDisplayNameOf(device_pidl, shellcon.SHGDN_NORMAL)
    name = None
    pidl = None

    v_print("Checking if %s is an iPhone." % device_name)

    folder = parent.BindToObject(device_pidl, None, shell.IID_IShellFolder)
    try:
        for pidl in folder.EnumObjects(0, shellcon.SHCONTF_FOLDERS):
            name = folder.GetDisplayNameOf(pidl, shellcon.SHGDN_NORMAL)
            break  # Only want to see the first folder.
        if name != "Internal Storage":
            return None, None, device_name
    except pywintypes.com_error:
        return None, None, device_name  # No problem, must not be an iPhone

    folder = folder.BindToObject(pidl, None, shell.IID_IShellFolder)
    for pidl in folder.EnumObjects(0, shellcon.SHCONTF_FOLDERS):
        name = folder.GetDisplayNameOf(pidl, shellcon.SHGDN_NORMAL)
        break  # Only want to see the first folder.
    if name != "DCIM":
        return None, None, device_name

    return pidl, folder, device_name


def get_destination_for_phone(localdir, iphone_name):
    """
    Read a YAML file that maps a phone's name to a local directory.
    :param iphone_name: The iPhone's name
    """
    names = yaml.load(file(os.path.join(localdir, "name-to-path.yaml"), "r"))
    for k in names:
        if k in iphone_name.lower():
            v_print("Local photo directory: %s" % (names[k], ))
            return names[k]
    return None


def index_from_filename(filename):
    """
    Return the index number in the filename
    :param filename: Filename of the form IMG_5555.JPG.
    """
    return int(filename[4:])


def get_prev_image(path):
    """
    Return the number in the filename of the most recent image already found
    in the specified directory.
    :param path: The path to search.
    """
    prev_index = -1
    for root, dirs, files in os.walk(path):
        for name in files:
            basename, ext = os.path.splitext(name)
            basename = basename.upper()
            ext = ext.upper()
            if ext == ".JPG" and basename.startswith("IMG_"):
                index = index_from_filename(basename)
                if prev_index < index:
                    prev_index = index
            elif ext == ".TXT":
                # Maybe it's a special .jpg.txt file.
                basename, ext = os.path.splitext(basename)
                if ext == ".JPG":
                    basename = basename[basename.find("IMG_"):]
                    index = index_from_filename(basename)
                    if prev_index < index:
                        prev_index = index

    v_print("The most recent image already on the computer had index %04d." %
            prev_index)
    return prev_index


def main(all_images):
    """
    Find a connected iPhone, and print the paths to images on it.
    :param all_images: Whether or not to list all images on the phone, or
                       only those newer than those found on disk.
    """
    start_time = time.time()
    localdir = os.path.abspath(os.path.dirname(sys.argv[0]))
    desktop = shell.SHGetDesktopFolder()

    # Find the iPhone in the Virtual Folder "Computer"
    for pidl in desktop.EnumObjects(0, shellcon.SHCONTF_FOLDERS):
        if desktop.GetDisplayNameOf(pidl, shellcon.SHGDN_NORMAL) == "Computer":
            folder = desktop.BindToObject(pidl, None, shell.IID_IShellFolder)
            for dpidl in folder:
                # If this is the iPhone, get the PIDL of its DCIM folder.
                dcim_pidl, parent, iphone_name = get_dcim_folder(dpidl, folder)
                if dcim_pidl is not None:
                    if all_images:
                        prev_index = -1
                    else:
                        dest = get_destination_for_phone(localdir, iphone_name)
                        prev_index = get_prev_image(dest)
                    walk_dcim_folder(dcim_pidl, parent, prev_index)
                    break
            break
    v_print("Done. That took %1.2fs." % (time.time() - start_time))


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-a", "--all", action="store_true")
    parser.set_defaults(verbose=False, all=False)
    args = parser.parse_args()
    set_v_print(args.verbose)
    main(args.all)
