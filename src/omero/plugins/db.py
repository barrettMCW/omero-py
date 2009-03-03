#!/usr/bin/env python
"""
   Plugin for our managing the OMERO database.

   Plugin read by omero.cli.Cli during initialization. The method(s)
   defined here will be added to the Cli class for later use.

   Copyright 2008 Glencoe Software, Inc. All rights reserved.
   Use is subject to license terms supplied in LICENSE.txt

"""

from exceptions import Exception
from omero.cli import Arguments, BaseControl, VERSION
from omero.java import run
import time

HELP=""" omero db [ script ]

Database tools:

     script - Generates a script for creating an OMERO database

"""
class DatabaseControl(BaseControl):

    def help(self, args = None):
        self.ctx.out(HELP)

    def _lookup(self, data, data2, key, map, hidden = False):
        """
        Read values from data and data2. If value is contained in data
        then use it without question. If the value is in data2, offer
        it as a default
        """
        map[key] = data.properties.getProperty("omero.db."+key)
        if not map[key] or map[key] == "":
            if data2:
                default = data2.properties.getProperty("omero.db."+key)
            else:
                default = ""
            map[key] = self.ctx.input("Please enter omero.db.%s [%s]: " % (key, default), hidden)
            if not map[key] or map[key] == "":
                map[key] = default
        if not map[key] or map[key] == "":
                self.ctx.die(1, "No value entered")

    def _get_password_hash(self):
        root_pass = None
        while not root_pass:
            root_pass = self.ctx.input("Please enter password for new OMERO root user: ", hidden = True)
            if root_pass == "":
                self.ctx.err("Password cannot be empty")
                continue
            confirm = self.ctx.input("Please re-enter password for new OMERO root user: ", hidden = True)
            if root_pass != confirm:
                self.ctx.err("Passwords don't match")
                continue
            break
        server_jar = self.ctx.dir / "lib" / "server" / "server.jar"
        return run(["-cp",str(server_jar),"ome.security.PasswordUtil",root_pass]).strip()

    def _copy(self, input_path, output, func):
            input = open(str(input_path))
            try:
                for s in input.xreadlines():
                        output.write(func(s))
            finally:
                input.close()

    def _make_replace(self, root_pass, db_vers, db_patch):
        def replace_method(str_in):
                str_out = str_in.replace("@ROOTPASS@",root_pass)
                str_out = str_out.replace("@DBVERSION@",db_vers)
                str_out = str_out.replace("@DBPATCH@",db_patch)
                return str_out
        return replace_method

    def _create(self, db_vers, db_patch, password_hash, location = None):
        sql_directory = self.ctx.dir / "sql" / "psql" / ("%s__%s" % (db_vers, db_patch))
        if not sql_directory.exists():
            self.ctx.die(2, "Invalid Database version/patch: %s does not exist" % sql_directory)

        script = "%s__%s.sql" % (db_vers, db_patch)
        if not location:
            location = self.ctx.dir / script

        output = open(location, 'w')
        print "Saving to " + location

        try:
            output.write("""
--
-- GENERATED %s from %s
--
-- This file was created by the bin/omero db script command
-- and contains an MD5 version of your OMERO root users's password.
-- You should think about deleting it as soon as possible.
--
-- To create your database:
--
--     createdb omero
--     createlang plpgsql omero
--     psql omero < %s
--

BEGIN;
            """ % ( time.ctime(time.time()), sql_directory, script ) )
            self._copy(sql_directory/"schema.sql", output, str)
            self._copy(sql_directory/"data.sql", output, self._make_replace(password_hash, db_vers, db_patch))
            self._copy(sql_directory/"views.sql", output, str)
            output.write("COMMIT;\n")
        finally:
            output.flush()
            output.close()

    def password(self, *args):
        args = Arguments(*args)
        password_hash = self._get_password_hash()
        self.ctx.out("""UPDATE password SET hash = '%s' WHERE experimenter_id = 0;""" % password_hash)

    def script(self, *args):
        args = Arguments(*args)

        data = self.ctx.initData({})
        try:
            data2 = self.ctx.initData({})
            output = self.ctx.readDefaults()
            self.ctx.parsePropertyFile(data2, output)
        except Exception, e:
            self.ctx.dbg(str(e))
            data2 = None
        map = {}
        self._lookup(data, data2, "version", map)
        self._lookup(data, data2, "patch", map)
        map["pass"] = self._get_password_hash()
        self._create(map["version"],map["patch"],map["pass"])

try:
    register("db", DatabaseControl)
except NameError:
    DatabaseControl()._main()
