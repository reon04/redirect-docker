import os
from flask import Flask, request, abort, send_from_directory, render_template
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
import mariadb

TABLE_NAME = "test"
FUNCTION_NAME = "uuid_v4"
MAX_URL_LENGTH = 512

resp_succ = {'response': "success"}
resp_err = {'response': "error"}

app = Flask(__name__, template_folder = 'httpdocs')
auth = HTTPBasicAuth()

http_users = {
    os.environ.get("HTTP_USER") or "test": generate_password_hash(os.environ.get("HTTP_PASS") or "test"),
}
db_host = os.environ.get("DB_HOST") or "localhost"
db_port = os.environ.get("DB_PORT") or "3306"
db_user = os.environ.get("DB_USER") or "test"
db_pass = os.environ.get("DB_PASS") or "test"
db_name = os.environ.get("DB_NAME") or "test"
connected = False

def db_connect():
  global dbconnector
  global db
  global connected
  if not connected:
    try:
      dbconnector = mariadb.connect(
        user=db_user,
        password=db_pass,
        host=db_host,
        port=int(db_port),
        database=db_name,
        autocommit=True
      )
    except mariadb.Error as e:
      print(f"Error connecting to MariaDB Platform: {e}")
    else:
      db = dbconnector.cursor()
      connected = True

def db_disconnect():
  dbconnector.close()

def db_exec(*args):
  global connected
  db_connect()
  if connected:
    try:
      db.execute(*args)
      return list(db.fetchall()), True
    except mariadb.Error as e:
      for e_msg in e.args:
        if e_msg == "Cursor doesn't have a result set":
          return list(), True
        if e_msg == "Server has gone away":
          connected = False
          break
      print(f"Error while executing MariaDB SQL Query: {e}")
  return list(), False

def check_missing_table_or_function():
  return len(db_exec(f"SHOW TABLES LIKE {TABLE_NAME}")) == 0 or len(db_exec(f"SHOW FUNCTIONS LIKE {FUNCTION_NAME}")) == 0

@auth.verify_password
def verify_password(username, password):
  if username in http_users and check_password_hash(http_users.get(username), password):
    return username

@app.route('/config', methods=['POST'])
@auth.login_required
def edit():
  req = request.json
  if req['action'] == "init" and not check_missing_table_or_function():
    db_exec(f"CREATE TABLE IF NOT EXISTS {TABLE_NAME} (id VARCHAR(32) NOT NULL, url VARCHAR({MAX_URL_LENGTH}) NOT NULL, new_win BOOLEAN NOT NULL, PRIMARY KEY (id)) ENGINE = InnoDB")
    db_exec(f"CREATE FUNCTION IF NOT EXISTS {FUNCTION_NAME} RETURNS CHAR(32) BEGIN RETURN LOWER(CONCAT(HEX(RANDOM_BYTES(4)), HEX(RANDOM_BYTES(2)), '4', SUBSTR(HEX(RANDOM_BYTES(2)), 2, 3), HEX(FLOOR(ASCII(RANDOM_BYTES(1)) / 64) + 8), SUBSTR(HEX(RANDOM_BYTES(2)), 2, 3), hex(RANDOM_BYTES(6)))); END;")
    if check_missing_table_or_function(): return resp_err
    else: return resp_succ
  ks = keys(req)
  if 'action' not in ks:
    return resp_err
  if req['action'] == "data":
    res, succ = db_exec("SELECT * FROM ?", (TABLE_NAME,))
    if succ: return {'response': "success", 'data': res}
    else: return resp_err
  if req['action'] == "new":
    if 'url' not in ks or 'new_win' not in ks: return resp_err
    if len(req['url']) > MAX_URL_LENGTH or str(req['new_win']).lower() not in ["true", "false", "1", "0"]: return resp_err
    succ = False
    res, succ = db_exec("INSERT INTO test VALUES('uuid_v4(), ?, ?)", (req['url'], req['new_win']))
    return resp_succ if succ else resp_err
  if req['action'] == "edit":
    if 'id' not in ks or 'url' not in ks or 'new_win' not in ks: return resp_err
    if len(req['url']) > MAX_URL_LENGTH or str(req['new_win']).lower() not in ["true", "false", "1", "0"]: return resp_err
    res, succ = db_exec(f"UPDATE {TABLE_NAME} SET url = ?, new_win = ? WHERE id = ?", (req['url'], req['new_win'], req['id']))
    return resp_succ if succ else resp_err
  if req['action'] == "delete":
    if 'id' not in ks: return resp_err
    res, succ = db_exec(f"DELETE FROM {TABLE_NAME} WHERE id = ?", (req['id'],))
    return resp_succ if succ else resp_err
  return resp_err

@app.route('/l/<path:id>', methods=['GET'])
def link(id):
  res, succ = db_exec(f"SELECT id, url, new_win FROM {TABLE_NAME} WHERE id = ?", (id,))
  if len(res) == 0: abort(404)
  url = res[0][1]
  new_win = res[0][2]
  if new_win: return render_template('link_new_win.html', link=url)
  else: return render_template('link_same_win.html', link=url)

@app.route('/')
@auth.login_required
def index():
  db_connect()
  if not connected: return send_from_directory('httpdocs', 'db_error.html')
  elif check_missing_table_or_function(): return send_from_directory('httpdocs', 'db_init.html')
  else: return send_from_directory('httpdocs', 'config.html')

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port="81")