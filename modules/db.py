import configparser
import MySQLdb

# Read config and parse constants
config = configparser.ConfigParser()
config.read('config.ini')


DB_SCHEMA = config.get('db', 'schema')
DB_HOST = config.get('db', 'host')
DB_USER = config.get('db', 'user')
DB_PW = config.get('db', 'pw')


def db_init():
    """
    Check for tables and triggers, if they don't exist, create them
    """
    if not check_db_exist():
        print("DB did not exist.")
        create_db()
    print("db did exist: {}".format(DB_SCHEMA))
    create_tables()
    create_triggers()


def check_db_exist():
    """
    Check if DB exists and return bool
    """
    db = MySQLdb.connect(host=DB_HOST, port=3306, user=DB_USER, passwd=DB_PW, use_unicode=True,
                         charset="utf8mb4")
    sql = "SHOW DATABASES LIKE '{}'".format(DB_SCHEMA)
    db_cursor = db.cursor()
    exists = db_cursor.execute(sql)
    db_cursor.close()
    db.close()

    return exists == 1


def create_db():
    """
    Create the schema if it doesn't exist
    """
    db = MySQLdb.connect(host=DB_HOST, port=3306, user=DB_USER, passwd=DB_PW, use_unicode=True,
                         charset="utf8mb4")
    db_cursor = db.cursor()
    sql = 'CREATE DATABASE IF NOT EXISTS {}'.format(DB_SCHEMA)
    db_cursor.execute(sql)
    db.commit()
    db_cursor.close()
    db.close()
    print('Created database')


def check_table_exists(table_name):
    """
    Check if the provided table exists
    """
    db = MySQLdb.connect(host=DB_HOST, port=3306, user=DB_USER, passwd=DB_PW, db=DB_SCHEMA, use_unicode=True,
                         charset="utf8mb4")
    db_cursor = db.cursor()
    sql = "SHOW TABLES LIKE '{}'".format(table_name)
    db_cursor.execute(sql)
    result = db_cursor.fetchall()
    db_cursor.close()
    db.close()
    return result


def create_triggers():
    """
    Create predefined triggers
    """
    db = MySQLdb.connect(host=DB_HOST, port=3306, user=DB_USER, passwd=DB_PW, db=DB_SCHEMA, use_unicode=True,
                         charset="utf8mb4")
    db_cursor = db.cursor()
    # TODO: Add triggers
    db.commit()
    db_cursor.close()
    db.close()


def create_tables():
    """
    Create predefined tables
    """
    db = MySQLdb.connect(host=DB_HOST, port=3306, user=DB_USER, passwd=DB_PW, db=DB_SCHEMA, use_unicode=True,
                         charset="utf8mb4")
    db_cursor = db.cursor()
    # TODO: Add tables
    exists = check_table_exists('users')
    if not exists:
        sql = """
              CREATE TABLE `users` (
                  `user_id` varchar(64) NOT NULL,
                  `username` varchar(45) DEFAULT NULL,
                  `address` varchar(64) DEFAULT NULL,
                  `balance` varchar(64) DEFAULT NULL,
                  `pending_withdraw` varchar(64) DEFAULT '0',
                  `notify` tinyint(1) DEFAULT NULL,
                  `block_number` int(64) DEFAULT '0',
                  PRIMARY KEY (`user_id`),
                  UNIQUE KEY `address_UNIQUE` (`address`)
              ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
              """
        db_cursor.execute(sql)
        print("Confirming user table created: {}".format(check_table_exists('users')))
    db.commit()
    db_cursor.close()
    db.close()


def get_db_data(db_call, values):
    """
    Retrieve data from DB
    """
    db = MySQLdb.connect(host=DB_HOST, port=3306, user=DB_USER, passwd=DB_PW, db=DB_SCHEMA, use_unicode=True,
                         charset="utf8mb4")
    db_cursor = db.cursor()
    db_cursor.execute(db_call, values)
    db_data = db_cursor.fetchall()
    db_cursor.close()
    db.close()
    return db_data


def set_db_data(db_call, values):
    """
    Enter data into DB
    """
    db = MySQLdb.connect(host=DB_HOST, port=3306, user=DB_USER, passwd=DB_PW, db=DB_SCHEMA, use_unicode=True,
                         charset="utf8mb4")
    try:
        db_cursor = db.cursor()
        db_cursor.execute(db_call, values)
        db.commit()
        db_cursor.close()
        db.close()
        return None
    except MySQLdb.ProgrammingError as e:
        return e
