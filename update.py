#!/usr/bin/env python
r"""
Creates a Kodi add-on repository from the specified add-on sources and the
current folder (The add-on repository), generating its textures files (in case
of a skin add-on), compressing and copying the needed files.

Usage: update.py [-h] [-d DATADIR] [-v]
                 [AddonPath [AddonPath ...]]

Positional arguments:
  AddonPath             path of the add-on:
                        * a ZIP file path
                        * a local folder path
                        * a Git repository URL (requires GitPython module)
                          FORMAT: Url[#Branch][:AddonPath]
                          - Url: Git repository URL
                          - Branch: The branch to clone
                              default: Currently active branch
                          - AddonPath: Relative path to the add-on root folder
                              default: Repository root folder

Optional arguments:
  -h, --help            show this help message and exit
  -d DATADIR, --datadir DATADIR
                        path to place the add-ons
                          default: Current folder
  -v, --version         show program's version number and exit

Example:
    update.py --datadir /kodi/repository.addons https://github.com/chadparry/kodi-repository.chad.parry.org.git:repository.chad.parry.org https://github.com/chadparry/kodi-plugin.program.remote.control.browser.git:plugin.program.remote.control.browser

Each add-on files are placed in its own named directory containing metadata and
ZIP files. In addition, the repository catalog "addons.xml.gz" and its checksum
file "addons.xml.gz.md5" is placed in the root folder.

Based on Chad Parry script:
    https://github.com/chadparry/kodi-repository.chad.parry.org/blob/fa21425ca5c740eea536ec4ff8b5ae911ab72458/tools/create_repository.py
"""

__license__ = "GNU GENERAL PUBLIC LICENSE. Version 2, June 1991"
__version__ = "1.0.0"

import argparse
import collections
import errno
import gzip
import hashlib
import io
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import traceback
import xml.etree.ElementTree
import zipfile

Addon = "addon"
AddonPublisherResult = collections.namedtuple("AddonPublisherResult", ("xml", "exception"))
Addons = Addon + "s"
Dot = '.'
XmlExtension = Dot + "xml"
AddonXml = Addon + XmlExtension
TextFileType = "txt"
ZipFileType = "zip"


def createFolder(path):
    if not os.path.isdir(path):
        os.mkdir(path)


def isUrl(path):
    return bool(re.match("[A-Za-z0-9+.-]+://.", path))


def getAddonInfo(addonXmlPath):
    # Parse addon.xml file.
    addonXml = xml.etree.ElementTree.parse(addonXmlPath).getroot()
    addonId = addonXml.get("id")
    # Validate the add-on ID.
    if (addonId is None or re.search("[^a-z0-9._-]", addonId)):
        raise RuntimeError("Invalid addon ID: " + addonId)
    addonVersion = addonXml.get("version")
    # Validate the add-on version.
    try:
        addonVersion = re.match(r"(\d+\.\d+\.\d+).*", addonVersion).groups()[0]
    except Exception:
        raise RuntimeError("Invalid addon version: " + addonVersion)
    return (addonId, addonVersion)


def getNameVersionFileName(path, name, version, fileType):
    return os.path.join(path, "%s-%s%s" % (name, version, Dot + fileType))


def onRmTreeError(func, path, exc_info):
    """
    Error handler for ``shutil.rmtree``.

    If the error is due to an access error (read only file)
    it attempts to add write permission and then retries.

    If the error is for another reason it re-raises the error.

    Usage : ``shutil.rmtree(path, onerror=onRmTreeError)``
    """
    # path is read-only...
    if not os.access(path, os.W_OK):
        # Add write presmission.
        os.chmod(path, stat.S_IWUSR)
        func(path)
    else:
        raise


def writeChecksumFile(filePath):
    checksum = hashlib.md5()
    with open(filePath, "rb") as file:
        for chunk in iter(lambda: file.read(4096), b""):
            checksum.update(chunk)
    with open(filePath + Dot + "md5", 'w') as md5File:
        md5File.write(checksum.hexdigest())


def fetch(addonPath, datadir, result):
    tempFolder = None
    try:
        changelog = "changelog"
        changelogFileName = changelog + Dot + TextFileType
        addonInfoFileNames = (AddonXml, "icon.png", "fanart.jpg", changelogFileName)
        # If addonPath is an URL...
        if isUrl(addonPath):
            # Parse addonPath using the format "Url[#Branch"[:AddonPath]]".
            (url, branch, addonRelativeFolderPath) = re.match("((?:[A-Za-z0-9+.-]+://)?.*?)(?:#([^#]*?))?(?::([^:]*))?$", addonPath).group(1, 2, 3)
            # Create a temporary folder for the Git cloned repository.
            addonPath = tempFolder = tempfile.mkdtemp()
            # Check out the sources.
            with git.Repo.clone_from(url, addonPath) as gitRepositoryCloned:
                if branch:
                    gitRepositoryCloned.git.checkout(branch)
            if addonRelativeFolderPath:
                addonPath = os.path.join(addonPath, addonRelativeFolderPath[1:])
        # If addonPath is a folder...
        if os.path.isdir(addonPath):
            addonXmlPath = os.path.join(addonPath, AddonXml)
            try:
                # If addon.xml file exists, get add-on info.
                if not os.path.isfile(addonXmlPath):
                    raise IOError(errno.ENOENT, "File not found", addonXmlPath)
                (addonId, addonVersion) = getAddonInfo(addonXmlPath)
                # If the OS is Windows and the add-on is skin, build textures.
                if platform.system() == "Windows" and addonId.startswith("skin."):
                    # Build skin media files and themes with Texturepacker.exe.
                    mediaFolder = os.path.join(addonPath, "media")
                    if os.path.isdir(mediaFolder):
                        themesFolder = os.path.join(addonPath, "themes")
                        # Create themesFolder.
                        createFolder(themesFolder)
                        # Move existing mediaFolder to themes dir
                        shutil.move(mediaFolder, os.path.join(themesFolder, "Textures"))
                        # Recreate empty mediaFolder.
                        os.makedirs(mediaFolder)
                        for item in os.listdir(themesFolder):
                            folder = os.path.join(themesFolder, item)
                            if os.path.isdir(folder):
                                subprocess.Popen(("TexturePacker.exe", "-dupecheck -input \"%s\" -output \"%s\"" % (folder, os.path.join(mediaFolder, "%s.xbt" % item)))).wait()
                        # Remove themesFolder.
                        shutil.rmtree(themesFolder)
                addonRepositoryFolder = os.path.join(datadir, addonId)
                # Create addonRepositoryFolder.
                createFolder(addonRepositoryFolder)
                # Create the compressed add-on ZIP archive.
                zipFilePath = getNameVersionFileName(addonRepositoryFolder, addonId, addonVersion, ZipFileType)
                if not os.path.isfile(zipFilePath):
                    with zipfile.ZipFile(zipFilePath, 'w', compression=zipfile.ZIP_DEFLATED) as zipFile:
                        # If addonPath is datadir, compress only the needed
                        # files.
                        if addonPath == datadir:
                            for addonInfoFileName in addonInfoFileNames:
                                addonInfoFilePath = os.path.join(addonPath, addonInfoFileName)
                                if os.path.isfile(addonInfoFilePath):
                                    zipFile.write(addonInfoFilePath, os.path.join(addonId, addonInfoFileName))
                        # Else, compress all files in folder
                        else:
                            for (addonFolder, addonFolderNames, fileNames) in os.walk(addonPath):
                                relativeFolder = os.path.join(addonId, os.path.relpath(addonFolder, addonPath))
                                for relativePath in fileNames:
                                    zipFile.write(os.path.join(addonFolder, relativePath), os.path.join(relativeFolder, relativePath))
                addonPath = zipFilePath
            finally:
                if (tempFolder and os.path.exists(tempFolder)):
                    shutil.rmtree(tempFolder, onerror=onRmTreeError)
        # If addonPath is a ZIP file...
        if zipfile.is_zipfile(addonPath):
            tempFolder = tempfile.mkdtemp()
            with zipfile.ZipFile(addonPath, 'r') as addonZip:
                addonXmlRegExp = re.compile(".*/" + AddonXml + '$', re.I)
                addonXmlZippedPath = next(filePath for filePath in addonZip.namelist() if addonXmlRegExp.match(filePath))
                addonZip.extract(addonXmlZippedPath, tempFolder)
            (addonId, addonVersion) = getAddonInfo(os.path.join(tempFolder, addonXmlZippedPath))
            shutil.rmtree(tempFolder)
            addonRepositoryFolder = os.path.join(datadir, addonId)
            addonRepositoryZipPath = os.path.join(addonRepositoryFolder, os.path.basename(addonPath))
            # Copy addonPath to addonRepositoryZipPath.
            if os.stat(addonPath) != os.stat(addonRepositoryZipPath):
                createFolder(addonRepositoryFolder)
                shutil.copyfile(addonPath, addonRepositoryZipPath)
            # Extract add-on files from addonRepositoryZipPath to
            # addonRepositoryFolder.
            with zipfile.ZipFile(addonRepositoryZipPath, 'r') as addonZip:
                addonZipFilePaths = addonZip.namelist()
                for addonFileName in addonInfoFileNames:
                    addonZipFilePath = addonId + '/' + addonFileName
                    if any(addonZipFilePath in fileName for fileName in addonZipFilePaths):
                        addonZip.extract(addonZipFilePath, datadir)
                changelogFilePath = os.path.join(addonRepositoryFolder, changelogFileName)
                # Rename changelog.txt to changelog-X.X.X.txt
                if os.path.isfile(changelogFilePath):
                    changelogVersionFilePath = getNameVersionFileName(addonRepositoryFolder, changelog, addonVersion, TextFileType)
                    if os.path.isfile(changelogVersionFilePath):
                        os.remove(changelogFilePath)
                    else:
                        os.rename(changelogFilePath, changelogVersionFilePath)
            # Write addon ZIP MD5 file.
            writeChecksumFile(addonRepositoryZipPath)
            addonXmlPath = os.path.join(addonRepositoryFolder, AddonXml)
            if os.path.isfile(addonXmlPath):
                result.append(AddonPublisherResult(xml.etree.ElementTree.parse(addonXmlPath).getroot(), None))
                os.remove(addonXmlPath)
    except Exception as exception:
        result.append(AddonPublisherResult(None, exception))


def getAddonPublisher(addonPath, datadir):
    result = []
    addonPublisher = collections.namedtuple("addonPublisher", ("thread", "result"))
    return addonPublisher(threading.Thread(name=addonPath, target=lambda: fetch(addonPath, datadir, result)), result)


def getErrorGettingAddon(addonName):
    return "Cannot download add-on \"%s\" and will not be included in the repository." % addonName


if __name__ == "__main__":
    # Parse arguments.
    parser = argparse.ArgumentParser(description="creates a Kodi add-on repository from the specified add-on sources.", formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("addonPaths", nargs='*', metavar="AddonPath", help="path of the add-on:\n* a %s file path\n* a local folder path\n* a Git repository URL (requires GitPython module)\n  FORMAT: Url[#Branch][:AddonPath]\n  - Url: Git repository URL\n  - Branch: The branch to clone\n      default: Currently active branch\n  - AddonPath: Relative path to the add-on root folder\n      default: Repository root folder" % ZipFileType.upper())
    # Set current path as the default add-ons data folder.
    currentFolder = os.path.dirname(os.path.abspath(__file__))
    parser.add_argument("-d", "--datadir", default=currentFolder, help="path to place the add-ons\n  default: %s" % currentFolder)
    parser.add_argument("-v", "--version", action="version", version="%(prog)s " + __version__)
    args = parser.parse_args()
    # If none AddonPath is provided, get currentFolder (repository add-on path)
    # and add-on paths in the repository README.md file.
    if not args.addonPaths:
        args.addonPaths.append(currentFolder)
        readmeFilePath = os.path.join(currentFolder, "README" + Dot + "md")
        if os.path.isfile(readmeFilePath):
            with open(readmeFilePath) as readmeFile:
                addonPathRegExp = re.compile("^\- \[.*?\]\((.*?)\)(.*?) ?(\w*)?$")
                for line in readmeFile.readlines():
                    addonPathResults = addonPathRegExp.match(line)
                    if addonPathResults:
                        addonPathGroups = addonPathResults.groups()
                        addonPath = addonPathGroups[0] + Dot + "git"
                        if addonPathGroups[2] is not None and addonPathGroups[2] != "":
                            addonPath += "#" + addonPathGroups[2]
                        if addonPathGroups[1] is not None and addonPathGroups[1] != "":
                            addonPath += ":" + addonPathGroups[1]
                        args.addonPaths.append(addonPath)
    # Import Git repositories.
    if any(isUrl(addonPath) for addonPath in args.addonPaths):
        try:
            global git
            import git
        except ImportError:
            raise RuntimeError("Please install GitPython with the following command: pip install gitpython")
    # If not exists, create args.datadir folder.
    if not os.path.isdir(args.datadir):
        os.mkdir(args.datadir)
    # Fetch all add-on sources in parallel and collect the results.
    addonPublishers = [getAddonPublisher(addonPath, args.datadir) for addonPath in args.addonPaths]
    for addonPublisher in addonPublishers:
        addonPublisher.thread.start()
    addonsXml = xml.etree.ElementTree.Element(Addons)
    for addonPublisher in addonPublishers:
        addonPublisher.thread.join()
        try:
            addonPublisherResult = next(iter(addonPublisher.result))
            if addonPublisherResult.exception is not None:
                print(getErrorGettingAddon(addonPublisher.thread.name))
                print(addonPublisherResult.exception)
            addonsXml.append(addonPublisherResult.xml)
        except StopIteration:
            print(getErrorGettingAddon(addonPublisher.thread.name))
    # Write addons.xml.gz file.
    addonsXmlPath = os.path.join(args.datadir, Addons + XmlExtension + Dot + "gz")
    # Write GZip file
    with io.BytesIO() as xmlFile:
        xml.etree.ElementTree.ElementTree(addonsXml).write(xmlFile, encoding="UTF-8", xml_declaration=True)
        with gzip.open(addonsXmlPath, "wb") as gzipFile:
            gzipFile.write(xmlFile.getvalue())
    # Write addons.xml.gz.md5 file.
    writeChecksumFile(addonsXmlPath)
