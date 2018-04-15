class MilestoneCache:

    def __init__(self, target):
        self._target = target
        self._milestone_cache = {}

        self._retrieve_from_gitlab()

    def __getitem__(self, label):
        milestone = self._milestone_cache.get(label)
        if milestone is None:
            milestone = self._target.get_project().milestones.create({
                'title': label
            })
            self._milestone_cache[milestone.title] = milestone

        return milestone

    def _retrieve_from_gitlab(self):
        for milestone in self._target.get_project().milestones.list():
            self._milestone_cache[milestone.title] = milestone
