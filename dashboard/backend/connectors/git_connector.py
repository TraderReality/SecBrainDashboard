"""
SECBrain Watcher

Git Runtime Connector
"""


import subprocess
from pathlib import Path



class GitConnector:

    def __init__(self, repository_path):

        self.repository_path = Path(repository_path).expanduser().resolve()


    def scan(self):

        try:

            result = subprocess.check_output(

                [
                    "git",
                    "tag"
                ],

                text=True,
                cwd=self.repository_path,
                stderr=subprocess.STDOUT,

            )


            tags = result.splitlines()


            frozen = [

                tag

                for tag in tags

                if "FROZEN" in tag

            ]


            return {

                "status":"READY",

                "repository":str(self.repository_path),

                "frozen":frozen

            }


        except Exception as e:


            return {

                "status":"ERROR",

                "repository":str(self.repository_path),

                "error":str(e)

            }
