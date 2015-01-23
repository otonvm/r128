# -*- coding: utf-8 -*-

__all__ = ["Database", "DatabaseError"]

from functools import partial
import hashlib
import json

import logger
log = logger.Logger(__name__)
log.level = "DEBUG"


class DatabaseError(Exception):
    pass


class Database:
    """Create or edit a json database.

    Instantiate with: Database(path)
        where path must be a string to an existing or future file on the filesystem.

    Args:
        raise_not_found: raise FileNotFoundError if an existing db is not found
        in_memory: never write a database file but keep all data in memory

    Raises:
        DatabaseError: the only exception that will be raised with a description
        of the error
        FileNotFoundError: if raise_not_found == True
    """
    def __init__(self, path, raise_not_found=False, in_memory=False):
        self.path = str(path)
        log.d("created Database with path: {}".format(self.path))

        self._raise_not_found = raise_not_found
        self._in_memory = in_memory

        # holds data of an existing database:
        self.db_data = None

        self._load()

    def _load(self):
        try:
            log.d("trying to open database")

            with open(self.path, mode='r') as f:
                self.db_data = json.load(f)

        except FileNotFoundError:
            log.d("existing database not found")
            if self._raise_not_found:
                raise FileNotFoundError("File {} not found.".format(self.path))

        except OSError:
            raise DatabaseError("Error while reading/writing the database.")
        except ValueError:
            raise DatabaseError("Error with argument to open().")

    def _commit(self):
        if not self._in_memory:
            try:
                log.d("trying to write database")

                with open(self.path, mode='w') as f:
                    json.dump(self.db_data, f, ensure_ascii=False, indent=4)

            except OSError:
                raise DatabaseError("Error while reading/writing the database.")
            except TypeError:
                raise DatabaseError("Could not commit data to the database.")
        else:
            log.d("skipping writing database file")

    def get_entry(self, md5):
        if self.db_data:
            try:
                return self.db_data[md5]
            except KeyError:
                log.d("entry for md5: {} not found".format(md5))
                return None
        else:
            return None

    def set_entry(self, md5, value):
        if self.db_data:
            if md5 not in self.db_data.keys():
                self.db_data[md5] = value
            else:
                log.d("value for md5 {} already present".format(md5))
                pass
            self._commit()

        else:
            self.db_data = dict()
            self.db_data[md5] = value
            self._commit()

    @staticmethod
    def md5sum(filename):
        with open(str(filename), mode='rb') as f:
            md5 = hashlib.md5()
            for buf in iter(partial(f.read, 128), b''):
                md5.update(buf)
        return md5.hexdigest()

    def __repr__(self):
        return self.db_data

    def __str__(self):
        return str(self.__repr__())
