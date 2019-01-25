#!/usr/bin/env python3

"""
Skeleton to use Dundas Rest API, with guaranteed log out.
"""
import contextlib
import logging
import requests
import sys


class DundasSession:
    """
    Using __new__ + contextlib.closing() is awesome.

    DundasSession can now be used within a context manager, meaning that whatever happens, its close() method
    will be called (thus logging out). No need to call logout() explicitely!
    Just using __del__ is not guaranteed to work because when __del__ is called, you do not know which objects
    are already destroyed, and the session object might well be dead.
    """
    def __new__(cls, *args, **kwargs):
        o=super().__new__(cls)
        o.__init__(*args, **kwargs)
        return contextlib.closing(o)

    def __init__(self, user, pwd, url):
        # For session reuse - TCP connection reuse, keeps cookies.
        self.s = requests.session()

        self.user = user
        self.pwd = pwd
        self.url = url
        self.api = self.url + '/api/'
        self.session_id = None  # Will bet set in login()

    def login(self):
        """Login and returns the session_id"""
        login_data = {
            'accountName': self.user,
            'password': self.pwd,
            'deleteOtherSessions': False,
            'isWindowsLogOn': False
        }
        logging.info('Logging in.')
        r = self.s.post(self.api + 'logon/', json=login_data)
        # The following line exceptions out on not 200 return code.
        r.raise_for_status()

        resp = r.json()
        if resp['logOnFailureReason'].lower() == "none":
            # We're in!
            logging.info('Logged in')
            self.session_id = resp['sessionId']
        else:
            logging.error('Login failed with message: ' + r.text)
            sys.exit(1)

    def close(self):
        """Automagically called by the context manager."""
        self.logout()

    def logout(self):
        """If you do not logout, session will stay active, potentially burning through your elastic hours very fast."""

        # If session_id is not defined, we did not even log in (or we are already logged out).
        logging.info('Logging out.')
        if getattr(self, 'session_id', None):
            r = self.s.delete(self.api + 'session/current', params={'sessionId': self.session_id})
            r.raise_for_status()
            del self.session_id
            logging.info('Logged out.')
        else:
            logging.info('Was not yet Logged in.')

logging.basicConfig(level='INFO')

with DundasSession(user='yourapiuser', pwd='pwd', url='https://reports.example.com') as dundas:
    dundas.login()

    # Do something smart with your Dundas object.

# No need to log out, this is handled for you via the context manager, even in case of exception or even sys.exit.
