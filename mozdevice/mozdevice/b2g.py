# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import datetime
import mozprofile
import os
import time
import socket
import StringIO
import subprocess
import sys

from marionette import Marionette
from mozdevice import DMError

class B2GManager(object):

    def __init__(self, dm, tmpdir=None, userJS=None, marionette_host=None, marionette_port=None):
        self.dm = dm
        self.tmpdir = tmpdir
        self.userJS = userJS or "/data/local/user.js"
        self.marionette_host = marionette_host or 'localhost'
        self.marionette_port = marionette_port or 2828
        self.marionette = None

    #timeout in seconds
    def wait_for_port(self, timeout):
        print "waiting for port"
        starttime = datetime.datetime.now()
        while datetime.datetime.now() - starttime < datetime.timedelta(seconds=timeout):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                print "trying %s %s" % (self.marionette_port, self.marionette_host)
                sock.connect((self.marionette_host, self.marionette_port))
                data = sock.recv(16)
                sock.close()
                if '"from"' in data:
                    print "got it"
                    return True
            except:
                import traceback
                print traceback.format_exc()
            time.sleep(1)
        return False

    def get_marionette(self):
        self.marionette = Marionette(self.marionette_host, self.marionette_port)

    def restart_b2g(self):
        #restart b2g so we start with a clean slate
        self.dm.checkCmd(['shell', 'stop', 'b2g'])
        # Wait for a bit to make sure B2G has completely shut down.
        time.sleep(10)
        self.dm.checkCmd(['shell', 'start', 'b2g'])

        #wait for marionette port to come up
        print "connect to marionette"
        if not self.wait_for_port(30):
            raise Exception("Could not communicate with Marionette port after restarting B2G")
        self.get_marionette()

    def set_tmpdir(self, tmpdir):
        self.tmpdir = tmpdir

    def setup_profile(self, prefs):
        if not self.tmpdir:
            raise Exception("You must set the tmpdir")
        #remove previous user.js if there is one
        our_user_js = os.path.join(self.tmpdir, "user.js")
        if os.path.exists(our_user_js):
            os.remove(our_user_js)
        #copy profile
        try:
            self.dm.checkCmd(["pull", self.userJS, our_user_js])
        except subprocess.CalledProcessError:
            pass
        #if we successfully copied the profile, make a backup of the file
        if os.path.exists(our_user_js):
            self.dm.checkCmd(['shell', 'dd', 'if=%s' % self.userJS, 'of=%s.orig' % self.userJS])
        print "opening userjs"
        user_js = open(our_user_js, 'a')
        print "Writing: %s" % prefs
        user_js.write("%s" % prefs)
        print "closing"
        user_js.close()
        self.dm.checkCmd(['push', our_user_js, self.userJS])
        self.restart_b2g()

    def forward_port(self):
        self.dm.checkCmd(['forward',
                          'tcp:%s' % self.marionette_port,
                          'tcp:%s' % self.marionette_port])

    def setup_ethernet(self):
        #TODO: need to add timeout
        tries = 3
        while tries > 0:
            print "on try: %d" % tries
            output = StringIO.StringIO()
            self.dm.shell(['ifconfig', 'eth0'], output)
            print "we get back %s" % output.getvalue()
            if "ip" in output.getvalue():
                return
            output.close()
            try:
                self.dm.checkCmd(['shell', 'netcfg', 'eth0', 'dhcp'], timeout=10)
            except DMError:
                pass
            tries = tries - 1
        raise DMError("Could not set up ethernet connection")

    def restore_profile(self):
        if not self.tmpdir:
            raise Exception("You must set the tmpdir")
        #if we successfully copied the profile, make a backup of the file
        our_user_js = os.path.join(self.tmpdir, "user.js")
        if os.path.exists(our_user_js):
            self.dm.checkCmd(['shell', 'dd', 'if=%s.orig' % self.userJS, 'of=%s' % self.userJS])

    def get_appinfo(self):
        if not self.marionette:
            self.forward_port()
            self.wait_for_port(30)
            self.get_marionette()
        self.marionette.start_session()
        self.marionette.set_context("chrome")
        appinfo = self.marionette.execute_script("""
                                var appInfo = Components.classes["@mozilla.org/xre/app-info;1"]
                                .getService(Components.interfaces.nsIXULAppInfo);
                                return appInfo;
                                """)
        (year, month, day) = (appinfo["appBuildID"][0:4], appinfo["appBuildID"][4:6], appinfo["appBuildID"][6:8])
        appinfo['date'] =  "%s-%s-%s" % (year, month, day)
        return appinfo
