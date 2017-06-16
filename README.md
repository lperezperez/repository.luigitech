# Luigitech Kodi Repository 0.0.0
Kodi repository for unofficial/modded/BETA addons.
### Update
To modify the add-ons included or make your own repository, follow these steps:
1. Clone this Git repository.
    ```bash
    $ git clone https://github.com/lperezperez/repository.luigitech.git
    ```
2. Update repository files.
    2.1. Update [README.md](https://github.com/lperezperez/repository.luigitech/blob/develop/README.md) adding/removing/modifying add-ons links. [update.py](https://github.com/lperezperez/repository.luigitech/blob/develop/update.py) will read the file, parsing the links with the following format:
    ```
    - [Add-on description](Git repository URL)/optional/relative/path/to/add-on/folder optional_branch_name
    ```
    2.2. Update [addon.xml](https://github.com/lperezperez/repository.luigitech/blob/develop/addon.xml) id, version, datadir...
3. Run the included [update.py](https://github.com/lperezperez/repository.luigitech/blob/develop/update.py)
    **GNU/Linux**
    ```bash
    $ ./update.py
    ```
    **Windows**
    ```
    $ python update.py
    ```
4. Publish changes to a remote Git repository.
5. Download the repository ZIP file and install through the Kodi repository installer plugin.
