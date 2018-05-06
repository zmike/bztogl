import json
import time
import urllib.parse

import gitlab


class GitLab:
    GITLABURL = "https://gitlab-test.gnome.org/"
    GIT_ORIGIN_PREFIX = 'https://git.gnome.org/browse/'

    def __init__(self, token, product, target_project=None, automate=False):
        self.gl = None
        self.token = token
        self.product = product
        self.target_project = target_project
        self.automate = automate
        self.all_users = None

    def connect(self):
        print("Connecting to %s" % self.GITLABURL)
        self.gl = gitlab.Gitlab(self.GITLABURL, self.token, api_version=4)
        self.gl.auth()
        # If not target project was given, set the project under the user
        # namespace
        if self.target_project is None:
            self.target_project = self.gl.user.username + '/' + self.product
            print("Using target project '{}' since --target-project was not"
                  " provided".format(self.target_project))

    def get_project(self):
        return self.gl.projects.get(self.target_project)

    def create_issue(self, id, summary, description, labels,
                     milestone, creation_time):
        payload = {
            'title': summary,
            'description': description,
            'labels': labels,
            'created_at': creation_time
        }

        if milestone:
            payload['milestone_id'] = milestone.id

        return self.get_project().issues.create(payload)

    def get_all_users(self):
        if self.all_users is None:
            self.all_users = self.gl.users.list(all=True)

        return self.all_users

    def find_user(self, user_id):
        return self.gl.users.get(user_id)

    def find_user_by_nick(self, nickname):
        for user in self.get_all_users():
            if user.attributes['username'] == nickname:
                return user

        return None

    def remove_project(self, project):
        try:
            project.delete()
        except Exception as e:
            raise Exception("Could not remove project: {}".format(project))

    def get_import_status(self, project):
        url = (self.GITLABURL +
               "api/v4/projects/{}".format(project.id))
        self.gl.session.headers = {"PRIVATE-TOKEN": self.token}
        ret = self.gl.session.get(url)
        if ret.status_code != 200:
            raise Exception("Could not get import status: {}".format(ret.text))

        ret_json = json.loads(ret.text)
        return ret_json.get('import_status')

    def import_project(self):
        import_url = self.GIT_ORIGIN_PREFIX + self.product
        print('Importing project from ' + import_url +
              ' to ' + self.target_project)

        try:
            project = self.get_project()
        except Exception as e:
            project = None

        if project is not None:
            print('##############################################')
            print('#                  WARNING                   #')
            print('##############################################')
            print('THIS WILL DELETE YOUR PROJECT IN GITLAB.')
            print('ARE YOU SURE YOU WANT TO CONTINUE? Y/N')

            if not self.automate:
                answer = input('')
            else:
                answer = 'Y'
                print('Y (automated)')

            if answer == 'Y':
                self.remove_project(project)
            else:
                print('Bugs will be added to the existing project')
                return

        project = self.gl.projects.create({'name': self.product,
                                           'import_url': import_url,
                                           'visibility': 'public'})

        import_status = self.get_import_status(project)
        while(import_status != 'finished'):
            print('Importing project, status: ' + import_status)
            time.sleep(1)
            import_status = self.get_import_status(project)

    def upload_file(self, filename, f):
        url = (self.GITLABURL +
               "api/v3/projects/{}/uploads".format(self.get_project().id))
        self.gl.session.headers = {"PRIVATE-TOKEN": self.token}
        ret = self.gl.session.post(url, files={
            'file': (urllib.parse.quote(filename), f)
        })
        if ret.status_code != 201:
            raise Exception("Could not upload file: {}".format(ret.text))
        return ret.json()
