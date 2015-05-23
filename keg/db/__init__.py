from __future__ import absolute_import
from __future__ import unicode_literals

from flask.ext.sqlalchemy import SQLAlchemy

from keg.signals import testing_run_start
from keg.utils import visit_modules


class KegSQLAlchemy(SQLAlchemy):

    def init_app(self, app):
        SQLAlchemy.init_app(self, app)
        if app.testing:
            self.testing_scoped_session()

        #@event.listens_for(Engine, "connect")
        #def on_connect(dbapi_connection, connection_record):
        #    self.dialect_util.on_connect(dbapi_connection, connection_record)

        #@testing_run_start.connect_via(ANY, weak=False)
        #def on_testing_start(app):
        #    self.dialect_util.on_testing_start(app)

    def testing_scoped_session(self):
        # don't want to have to import this if we are in production, so put import
        # inside of the method
        from flask.ext.webtest import get_scopefunc

        # flask-sqlalchemy creates the session when the class is initialized.  We have to re-create
        # with different session options and override the session attribute with the new session
        db.session = db.create_scoped_session(options={'scopefunc': get_scopefunc()})

    def get_engines(self, app):
        bind_names = app.config.get('SQLALCHEMY_BINDS', {}).keys()
        retval = [(None, self.get_engine(app))]
        for bind_name in bind_names:
            retval.append((bind_name, self.get_engine(app, bind=bind_name)))
        return retval

db = KegSQLAlchemy()

# put this import after the above db assignment to avoid circular reference issues
from .dialect_ops import DialectOperations


class DatabaseManager(object):
    """
        A per-app-instance utility class that managers all common operations for a Keg app.

        Binds & Dialects
        ----------------

        Flask SQLAlchemy handles multiple DB connections per application through the use of "binds."
        When an application wants to communicate events or initiate activites, this manager will
        will handle distributing those events and activities to all database connections bound
        to the application.

        Furthermore, this manager delegates to DialectOperations instances to run the events and
        activities in ways that are specific to the type of RDBMS being used (when needed).
    """

    def __init__(self, app):
        self.app = app
        self.dialect_opts = app.config['KEG_DB_DIALECT_OPTIONS']

        self.init_app()
        self.init_events()

    def init_app(self):
        db.init_app(self.app)
        visit_modules(self.app.db_visit_modules, self.app.import_name)

    def init_events(self):
        testing_run_start.connect(self.on_testing_start, sender=self.app)

    def bind_dialect(self, bind_name):
        engine = db.get_engine(self.app, bind=bind_name)
        return DialectOperations.create_for(engine, bind_name, self.dialect_opts)

    def all_bind_dialects(self):
        """
            For each database connection (bind) in this application, yield a DialectOperations
            instance corresponding to the type of RDBMS the bind is connecting to.
        """
        for bind_name, engine in db.get_engines(self.app):
            yield DialectOperations.create_for(engine, bind_name, self.dialect_opts)

    def on_testing_start(self, app):
        for dialect in self.all_bind_dialects():
            dialect.on_testing_start()

    def drop_all(self):
        for dialect in self.all_bind_dialects():
            dialect.drop_all()
