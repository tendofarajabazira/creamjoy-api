from flask import Flask
from flask_mysqldb import MySQL
from app.config import Config

mysql = MySQL()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    mysql.init_app(app)

    from app.routes.main import main
    app.register_blueprint(main)

    return app
