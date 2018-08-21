import json
import time
import urllib.parse

import gitlab


class GitLab:
    def __init__(self, gitlab_url, git_url, token, product,
                 target_project=None, automate=False):
        self.gl = None
        self.gl_url = gitlab_url
        self.git_url = git_url
        self.token = token
        self.product = product
        self.target_project = target_project
        self.automate = automate
        self.all_users = None
        self.all_users_map = {}
        self.project = None
        self.milestones = {}
        self.labels = {}

    def connect(self):
        print("Connecting to %s" % self.gl_url)
        self.gl = gitlab.Gitlab(self.gl_url, self.token, api_version=4)
        self.gl.auth()
        # If not target project was given, set the project under the user
        # namespace
        if self.target_project is None:
            self.target_project = self.gl.user.username + '/' + self.product
            print("Using target project '{}' since --target-project was not"
                  " provided".format(self.target_project))

    def get_project(self):
        if not self.project:
            self.project = self.gl.projects.get(self.target_project)
        return self.project

    def create_issue(self, id, summary, description, labels,
                     milestone, creation_time, sudo=None):
        payload = {
            'title': summary,
            'description': description,
            'labels': labels,
            'created_at': creation_time
        }

        if milestone:
            if not milestone in self.milestones:
                try:
                    gl_milestone = self.get_project().milestones.create({'title': milestone})
                except:
                    print("milestone %s already exists" % (milestone))
                    gl_milestones = self.get_project().milestones.list(search=milestone)
                    gl_milestone = gl_milestones[0]
                self.milestones[milestone] = gl_milestone
            gl_milestone = self.milestones[milestone]
            payload['milestone_id'] = gl_milestone.id

        if labels:
            for label in labels:
                if not label in self.labels:
                    try:
                       self.get_project().labels.create({'name': label, 'color': '#428BCA'})
                    except:
                       print("label %s already exists" % (label))
                       self.labels[label] = True

        return self.get_project().issues.create(payload, sudo=sudo)

    def create_mergerequest(self, id, summary, description, labels,
                     milestone, sudo=None):
        payload = {
            'title': summary,
            'description': description,
            'labels': labels,
            'source_branch': "phab-" + str(id),
            'target_branch': 'master'
        }

        if milestone:
            if not milestone in self.milestones:
                try:
                    gl_milestone = self.get_project().milestones.create({'title': milestone})
                except:
                    print("milestone %s already exists" % (milestone))
                    gl_milestones = self.get_project().milestones.list(search=milestone)
                    gl_milestone = gl_milestones[0]
                self.milestones[milestone] = gl_milestone
            gl_milestone = self.milestones[milestone]
            payload['milestone_id'] = gl_milestone.id

        if labels:
            for label in labels:
                if not label in self.labels:
                    try:
                       self.get_project().labels.create({'name': label, 'color': '#428BCA'})
                    except:
                       print("label %s already exists" % (label))
                       self.labels[label] = True

        return self.get_project().mergerequests.create(payload, sudo=sudo)

    def create_user(self, user_id):
        return self.gl.users.create({'email': '{}@localhost'.format(user_id),
            'reset_password': 'true',
            'username': user_id,
            'name': user_id})

    def get_all_users(self):
        if self.all_users is None:
            self.all_users = self.gl.users.list(all=True)
            for user in self.all_users:
                print("adding user to cache %s" % (user.attributes['username']))
                self.all_users_map[user.attributes['username']] = user

        return self.all_users

    def find_issue(self, title, creation_time):
        return self.get_project().issues.list(search=title, created_after=creation_time)

    def find_patch(self, title, creation_time):
        return self.get_project().mergerequests.list(search=title)

    def find_user(self, user_id):
        return self.gl.users.get(user_id)

    def find_user_by_nick(self, nickname):
        if self.all_users == None:
            self.get_all_users()

        if nickname in self.all_users_map:
            return self.all_users_map[nickname]
        return None

    def remove_project(self, project):
        try:
            project.delete()
        except Exception as e:
            raise Exception("Could not remove project: {}".format(project))

    def get_import_status(self, project):
        url = ("{}api/v4/projects/{}".format(self.gl_url, project.id))
        self.gl.session.headers = {"PRIVATE-TOKEN": self.token}
        ret = self.gl.session.get(url)
        if ret.status_code != 200:
            raise Exception("Could not get import status: {}".format(ret.text))

        ret_json = json.loads(ret.text)
        return ret_json.get('import_status')

    def import_project(self):
        import_url = self.git_url + self.product
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
        url = "{}api/v4/projects/{}/uploads".format(self.gl_url,
                                                    self.get_project().id)
        self.gl.session.headers = {"PRIVATE-TOKEN": self.token}
        ret = self.gl.session.post(url, files={
            'file': (urllib.parse.quote(filename), f)
        })
        if ret.status_code != 201:
            raise Exception("Could not upload file: {}".format(ret.text))
        return ret.json()
