import os, gc
from .httpclient import HttpClient

class OTAUpdater:

    def __init__(self, github_repo, github_src_dir='', module='', main_dir='main', new_version_dir='next', secrets_file=None, headers={}, file_list_name='ota_files.txt'):
        self.http_client = HttpClient(headers=headers)
        self.github_repo = github_repo.rstrip('/').replace('https://github.com/', '')
        self.github_src_dir = '' if len(github_src_dir) < 1 else github_src_dir.rstrip('/') + '/'
        self.module = module.rstrip('/')
        self.main_dir = main_dir
        self.new_version_dir = new_version_dir
        self.secrets_file = secrets_file
        self.file_list_name = file_list_name

    def __del__(self):
        self.http_client = None

    def check_for_update_to_install_during_next_reboot(self) -> bool:
        (current_version, latest_version) = self._check_for_new_version()
        if latest_version > current_version:
            print('New version available, will download and install on next reboot')
            self._create_new_version_file(latest_version)
            return True

        return False

    def install_update_if_available_after_boot(self, ssid, password) -> bool:
        if self.new_version_dir in os.listdir(self.module):
            if '.version' in os.listdir(self.modulepath(self.new_version_dir)):
                latest_version = self.get_version(self.modulepath(self.new_version_dir), '.version')
                print('New update found: ', latest_version)
                OTAUpdater._using_network(ssid, password)
                self.install_update_if_available()
                return True
            
        print('No new updates found...')
        return False

    def install_update_if_available(self):
        (current_version, latest_version) = self._check_for_new_version()
        if latest_version > current_version:
            print('Updating to version {}...'.format(latest_version))
            self._create_new_version_file(latest_version)
            self._download_new_version(latest_version)
            self._copy_secrets_file()
            self._delete_old_version()
            self._install_new_version()
            return (True, latest_version)
        print('No new version found, current {} is ok'.format(current_version))
        return (False, current_version)


    @staticmethod
    def _using_network(ssid, password):
        import network
        sta_if = network.WLAN(network.STA_IF)
        if not sta_if.isconnected():
            print('connecting to network...')
            sta_if.active(True)
            sta_if.connect(ssid, password)
            while not sta_if.isconnected():
                pass
        print('network config:', sta_if.ifconfig())

    def _check_for_new_version(self):
        current_version = self.get_version(self.modulepath('/'))
        latest_version = self.get_latest_version()

        print('Checking version... ')
        print('\tCurrent version {}, latest version {}'.format(current_version, latest_version))
        return (current_version, latest_version)

    def _create_new_version_file(self, latest_version):
        self.mkdir(self.modulepath(self.new_version_dir))
        with open(self.modulepath(self.new_version_dir + '/.version'), 'w') as versionfile:
            versionfile.write(latest_version)
            versionfile.close()

    def get_version(self, directory, version_file_name='.version'):
        if version_file_name in os.listdir(directory):
            with open(directory + '/' + version_file_name) as f:
                version = f.read()
                return version
        return '0.0'

    def get_latest_version(self):
        latest_release = self.http_client.get('https://api.github.com/repos/{}/releases/latest'.format(self.github_repo))
        version = latest_release.json()['tag_name']
        latest_release.close()
        return version

    def _download_new_version(self, version):
        print('Downloading version {}'.format(version))
        #version = 'main' # force master branch for testing
        file_list = self.download_explicit_file_list(version)
        if file_list:
            self.download_by_file_list(file_list, version)
        else:
            self._download_all_files(version)
        print('Version {} downloaded to {}'.format(version, self.modulepath(self.new_version_dir)))

    def download_explicit_file_list(self, version):
        url = 'https://raw.githubusercontent.com/{}/{}/{}'.format(self.github_repo, version, self.file_list_name)
        file_list = None
        file_list_response = self.http_client.get(url)
        if file_list_response.status_code == 200:
            file_list = file_list_response.text.split('\n')
        file_list_response.close()
        return file_list
    
    def download_by_file_list(self, file_list, version):
        for file_path in file_list:
            complete_file_path = self.modulepath(self.new_version_dir + '/' + file_path)
            path_and_file = complete_file_path.rsplit('/', 1)
            path = None
            git_path = None
            if len(path_and_file) == 1:
                path = self.new_version_dir
                git_path = path_and_file[0]
            else:
                git_path = self.github_src_dir + file_path
                path = complete_file_path
                target_dir = path_and_file[0]
                self._mk_dirs(target_dir)
            print('\tDownloading: ', git_path, 'to', path)
            self._download_file(version, git_path, path)

    def _download_all_files(self, version, sub_dir=''):
        url = 'https://api.github.com/repos/{}/contents{}{}{}?ref=refs/tags/{}'.format(self.github_repo, self.github_src_dir, self.main_dir, sub_dir, version)
        gc.collect() 
        file_list = self.http_client.get(url)
        for file in file_list.json():
            path = self.modulepath(self.new_version_dir + '/' + file['path'].replace(self.main_dir + '/', '').replace(self.github_src_dir, ''))
            if file['type'] == 'file':
                gitPath = file['path']
                print('\tDownloading: ', gitPath, 'to', path)
                self._download_file(version, gitPath, path)
            elif file['type'] == 'dir':
                print('Creating dir', path)
                self.mkdir(path)
                self._download_all_files(version, sub_dir + '/' + file['name'])
            gc.collect()

        file_list.close()

    def _download_file(self, version, gitPath, path):
        file_url = 'https://raw.githubusercontent.com/{}/{}/{}'.format(self.github_repo, version, gitPath)
        self.http_client.get(file_url, saveToFile=path)

    def _copy_secrets_file(self):
        if self.secrets_file:
            fromPath = self.modulepath(self.main_dir + '/' + self.secrets_file)
            toPath = self.modulepath(self.new_version_dir + '/' + self.main_dir + '/' + self.secrets_file)
            self._copy_file(fromPath, toPath)
            print('Copied secrets file from {} to {}'.format(fromPath, toPath))

    def _delete_old_version(self):
        self._rmtree(self.modulepath(self.main_dir))
        print('Deleted old version at {} ...'.format(self.modulepath(self.main_dir)))

    def _install_new_version(self):
        print('Installing new version from {} to {} ...'.format(self.modulepath(self.new_version_dir), self.modulepath(self.main_dir)))
        self._copy_directory(self.modulepath(self.new_version_dir), self.modulepath('/'))
        self._rmtree(self.modulepath(self.new_version_dir))
        print('Update installed, please reboot now')

    def _rmtree(self, directory):
        for entry in os.ilistdir(directory):
            is_dir = entry[1] == 0x4000
            if is_dir:
                self._rmtree(directory + '/' + entry[0])
            else:
                os.remove(directory + '/' + entry[0])
        os.rmdir(directory)

    def _copy_directory(self, fromPath, toPath):
        if not self._exists_dir(toPath):
            self._mk_dirs(toPath)

        for entry in os.ilistdir(fromPath):
            is_dir = entry[1] == 0x4000
            if is_dir:
                self._copy_directory(fromPath + '/' + entry[0], toPath + '/' + entry[0])
            else:
                self._copy_file(fromPath + '/' + entry[0], toPath + '/' + entry[0])

    def _copy_file(self, fromPath, toPath):
        with open(fromPath) as fromFile:
            with open(toPath, 'w') as toFile:
                CHUNK_SIZE = 512 # bytes
                data = fromFile.read(CHUNK_SIZE)
                while data:
                    toFile.write(data)
                    data = fromFile.read(CHUNK_SIZE)
            toFile.close()
        fromFile.close()

    def _exists_dir(self, path) -> bool:
        try:
            os.listdir(path)
            return True
        except:
            return False

    def _mk_dirs(self, path:str):
        paths = path.split('/')

        pathToCreate = ''
        for x in paths:
            self.mkdir(pathToCreate + x)
            pathToCreate = pathToCreate + x + '/'

    def mkdir(self, path:str):
        try:
            os.mkdir(path)
        except OSError as exc:
            if exc.args[0] == 17: 
                pass

    def modulepath(self, path):
        return self.module + '/' + path if self.module else path