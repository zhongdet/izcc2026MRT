import logging
from flask_socketio import SocketIO


log = logging.getLogger(__name__)
socketio = SocketIO(cors_allowed_origins="*", allow_upgrades=False)


@socketio.on("Connect")
def connect(data):
    log.info(data["message"])
    socketio.emit("Connected", {"message": "Connected from server"})
