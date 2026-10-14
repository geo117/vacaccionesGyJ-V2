import os
import io
import json
import secrets
from datetime import datetime
import pyodbc
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

# Cargar variables de entorno
load_dotenv()

app = Flask(__name__)
CORS(app, origins="*")
socketio = SocketIO(app, cors_allowed_origins="*")

# Configuración de la base de datos (lectura - PBI)
DB_SERVER = os.getenv('DB_SERVER')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_DRIVER = os.getenv('DB_DRIVER')

def get_db_connection():
    try:
        conn_str = (
            f"DRIVER={DB_DRIVER};"
            f"SERVER={DB_SERVER};"
            f"DATABASE={DB_NAME};"
            f"UID={DB_USER};"
            f"PWD={DB_PASSWORD}"
        )
        conn = pyodbc.connect(conn_str)
        return conn
    except Exception as e:
        print(f"Error de conexión BD1: {e}")
        return None

# Configuración de la base de datos (escritura - vacacionesgyj)
DB_SERVER2 = os.getenv('DB_SERVER2')
DB_NAME2 = os.getenv('DB_NAME2')
DB_USER2 = os.getenv('DB_USER2')
DB_PASSWORD2 = os.getenv('DB_PASSWORD2')
DB_DRIVER2 = os.getenv('DB_DRIVER2')

def get_db_connection2():
    try:
        conn_str = (
            f"DRIVER={DB_DRIVER2};"
            f"SERVER={DB_SERVER2};"
            f"DATABASE={DB_NAME2};"
            f"UID={DB_USER2};"
            f"PWD={DB_PASSWORD2}"
        )
        conn = pyodbc.connect(conn_str)
        return conn
    except Exception as e:
        print(f"Error de conexión BD2: {e}")
        return None

def guardar_notificacion_db(unes, titulo, mensaje):
    """
    Guarda una notificación en la base de datos (BD2) y la emite por socket.
    Se usa para acciones como aprobado, rechazado y asignación de fechas.
    """
    conn = get_db_connection2()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO notificaciones (unes_notificacion, titulo, mensaje, leida)
                VALUES (?, ?, ?, 0)
            """, (unes, titulo, mensaje))
            conn.commit()
            cursor.close()
            conn.close()
            
            # Emitir la notificación en tiempo real a través de Socket.io
            send_notification(f"{titulo}: {mensaje}", unes=unes, type="success" if "Aprobado" in titulo else "info")
            return True
        except Exception as e:
            print(f"Error al guardar notificación en DB: {e}")
            return False
    return False

# Eventos de Socket.IO
@socketio.on('connect')
def handle_connect():
    print('Cliente conectado')
    emit('connected', {'message': 'Conectado al servidor de notificaciones'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Cliente desconectado')

@socketio.on('approve_request')
def handle_approve_request(data):
    unes = data.get('unes')
    nombre = data.get('nombre')
    guardar_notificacion_db(unes, 'Solicitud Aprobada', f'La solicitud de {nombre} ha sido aprobada.')

@socketio.on('reject_request')
def handle_reject_request(data):
    unes = data.get('unes')
    nombre = data.get('nombre')
    motivo = data.get('motivo')
    guardar_notificacion_db(unes, 'Solicitud Rechazada', f'La solicitud de {nombre} fue rechazada. Motivo: {motivo}')

@socketio.on('assign_dates')
def handle_assign_dates(data):
    unes = data.get('unes')
    nombre = data.get('nombre')
    guardar_notificacion_db(unes, 'Fechas Asignadas', f'Se han asignado nuevas fechas de vacaciones para {nombre}.')

@socketio.on('request_notifications')
def handle_request_notifications():
    conn = get_db_connection2()
    notifications = []
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT TOP 20 
                    unes_notificacion, titulo, mensaje, leida, fecha_notificacion
                FROM notificaciones
                WHERE leida = 0
                ORDER BY fecha_notificacion DESC
            """)
            rows = cursor.fetchall()
            for row in rows:
                notifications.append({
                    'id': len(notifications) + 1,
                    'unes': row.unes_notificacion,
                    'text': row.mensaje,
                    'type': row.titulo,
                    'time': format_time(row.fecha_notificacion)
                })
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Error al obtener notificaciones: {e}")
    emit('notifications', notifications)

def format_time(fecha):
    from datetime import datetime
    if not fecha:
        return 'Hace un momento'
    try:
        fecha_dt = datetime.strptime(str(fecha), '%Y-%m-%d %H:%M:%S')
        from datetime import timedelta
        diff = datetime.now() - fecha_dt
        if diff.total_seconds() < 60:
            return 'Hace un momento'
        elif diff.total_seconds() < 3600:
            mins = int(diff.total_seconds() / 60)
            return f'Hace {mins} min'
        elif diff.total_seconds() < 86400:
            hours = int(diff.total_seconds() / 3600)
            return f'Hace {hours} hora{"s" if hours > 1 else ""}'
        else:
            days = int(diff.total_seconds() / 86400)
            return f'Hace {days} día{"s" if days > 1 else ""}'
    except:
        return 'Hace un momento'

def send_notification(text, unes=None, type='info'):
    socketio.emit('new_notification', {
        'id': 1,
        'unes': unes,
        'text': text,
        'type': type,
        'time': 'Hace un momento'
    })

@app.route('/marcar_notificaciones_leidas', methods=['POST'])
def marcar_notificaciones_leidas():
    data = request.get_json(silent=True) or {}
    unes = data.get('unes')
    conn = get_db_connection2()
    if not conn:
        return jsonify({'ok': False, 'error': 'No se pudo conectar a vacacionesgyj'}), 500
    try:
        cursor = conn.cursor()
        if unes:
            cursor.execute(
                "UPDATE notificaciones SET leida = 1 WHERE leida = 0 AND unes_notificacion = ?",
                (str(unes),)
            )
        else:
            cursor.execute("UPDATE notificaciones SET leida = 1 WHERE leida = 0")
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'ok': True, 'message': 'Notificaciones marcadas como leídas'}), 200
    except Exception as e:
        print(f"Error al marcar notificaciones leídas: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/usuarios_nuevos', methods=['POST'])
def usuarios_nuevos():
    """Registra un nuevo usuario en vacacionesgyj.dbo.users."""
    conn = get_db_connection2()
    if not conn:
        return jsonify({'ok': False, 'error': 'No se pudo conectar a vacacionesgyj'}), 500
    try:
        data = request.get_json(silent=True) or {}

        nombre = (data.get('nombre') or '').strip()
        correo = (data.get('correo') or '').strip()
        cargo = data.get('cargo')
        password = data.get('password')
        unes = data.get('unes')
        activo = data.get('activo', True)

        if not nombre or not correo:
            return jsonify({'ok': False, 'error': 'El nombre y el correo son obligatorios'}), 400

        cursor = conn.cursor()

        # Evitar duplicados por correo
        cursor.execute("SELECT 1 FROM users WHERE correo = ?", (correo,))
        if cursor.fetchone():
            cursor.close()
            return jsonify({'ok': False, 'error': 'Ya existe un usuario con ese correo'}), 409

        # Generar hash seguro para la contraseña
        password_hash = generate_password_hash(password) if password else None

        cursor.execute("""
            INSERT INTO users (Nombres, correo, cargo, password, unes, Activo, FechaCreacion)
            VALUES (?, ?, ?, ?, ?, ?, GETDATE())
        """, (nombre, correo, cargo, password_hash, unes, 1 if activo else 0))

        conn.commit()
        cursor.close()
        return jsonify({'ok': True, 'message': 'Usuario registrado correctamente'}), 200
    except Exception as e:
        print(f"Error en usuarios_nuevos: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

def es_password_hash(valor):
    """
    Detecta si un valor almacenado en users.password es un hash unidireccional
    (werkzeug pbkdf2/scrypt/argon2 o bcrypt) en lugar de texto plano.
    """
    if valor is None:
        return False
    v = str(valor).strip().lower()
    if not v:
        return False
    prefijos_hash = ('pbkdf2:', 'scrypt:', 'argon2', 'pbkdf2-sha256$', '$2a$', '$2b$', '$2y$')
    return v.startswith(prefijos_hash)


@app.route('/get_usuario_password/<int:id>', methods=['GET'])
def get_usuario_password(id):
    """
    Devuelve la contraseña en texto plano SOLO si el registro no está hasheado.

    Si users.password contiene un hash unidireccional (pbkdf2/bcrypt/argon2) el
    valor original es matemáticamente irrecuperable, por lo que se responde con
    has_password=True, password_is_hashed=True y password=None. Nunca se
    devuelve la cadena del hash.
    """
    conn = get_db_connection2()
    if not conn:
        return jsonify({'ok': False, 'error': 'No se pudo conectar a vacacionesgyj'}), 500
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE id = ?", (id,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'ok': False, 'error': 'Usuario no encontrado'}), 404

        stored = row[0] or ''
        hashed = es_password_hash(stored)

        return jsonify({
            'ok': True,
            'has_password': bool(str(stored).strip()),
            'password_is_hashed': hashed,
            # None cuando es hash: no hay forma de recuperar el original.
            'password': None if hashed else str(stored),
        }), 200
    except Exception as e:
        print(f"Error en get_usuario_password: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass


@app.route('/login', methods=['POST'])
def login():
    """
    Valida las credenciales contra vacacionesgyj.dbo.users.

    La comparación se hace SIEMPRE en el backend con check_password_hash, de modo
    que el hash nunca viaja al navegador. Se soporta tambien el caso legado de
    usuarios cuya contraseña quedó guardada en texto plano.
    """
    conn = get_db_connection2()
    if not conn:
        return jsonify({'ok': False, 'error': 'No se pudo conectar a vacacionesgyj'}), 500
    try:
        payload = request.get_json(silent=True) or {}
        correo = (payload.get('correo') or '').strip().lower()
        password = payload.get('password') or ''
        unes_ingresada = (payload.get('unes') or '').strip()

        if not correo or not password:
            return jsonify({'ok': False, 'error': 'Correo y contraseña son obligatorios'}), 400

        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, Nombres, correo, unes, password, cargo, Activo FROM users WHERE LOWER(correo) = ?",
            (correo,)
        )
        row = cursor.fetchone()

        if not row:
            # Respuesta generica para no enumerar correos validos.
            return jsonify({'ok': False, 'error': 'Credenciales inválidas'}), 401

        usuario = {
            'id': row[0],
            'nombre': row[1] or '',
            'correo': row[2] or '',
            'unes': (row[3] or ''),
            'password': row[4] or '',
            'cargo': row[5] or '',
            'Activo': bool(row[6]) if row[6] is not None else False,
        }

        if not usuario['Activo']:
            return jsonify({'ok': False, 'error': 'Usuario inactivo. Contacte al administrador.'}), 403

        stored = usuario['password']
        if es_password_hash(stored):
            password_valida = check_password_hash(stored, password)
        else:
            # Comparacion en tiempo constante tambien para el caso legado.
            password_valida = secrets.compare_digest(str(stored), str(password))

        if not password_valida:
            return jsonify({'ok': False, 'error': 'Credenciales inválidas'}), 401

        unes_usuario = str(usuario['unes']).strip()
        if unes_ingresada and unes_usuario:
            if not (unes_usuario.endswith(unes_ingresada) or unes_usuario == unes_ingresada):
                return jsonify({'ok': False, 'error': 'La UNES no corresponde al usuario.'}), 401

        # No se devuelve password: solo lo minimo necesario para la sesion.
        return jsonify({
            'ok': True,
            'user': {
                'nombre': usuario['nombre'],
                'correo': usuario['correo'],
                'unes': unes_usuario,
            }
        }), 200
    except Exception as e:
        print(f"Error en login: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass


@app.route('/get_usuarios', methods=['GET'])
def get_usuarios():
    """
    Devuelve los usuarios registrados en vacacionesgyj.dbo.users.

    IMPORTANTE: nunca se expone el valor de users.password. Solo se informa
    si el usuario tiene contraseña asignada mediante el flag 'has_password'.
    """
    conn = get_db_connection2()
    if not conn:
        return jsonify({'ok': False, 'error': 'No se pudo conectar a vacacionesgyj'}), 500
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                id,
                Nombres,
                correo,
                unes,
                password,
                cargo,
                Activo,
                FechaCreacion
            FROM users
            ORDER BY id DESC
        """)
        rows = cursor.fetchall()
        columns = [col[0] for col in (cursor.description or [])]

        def fmt_date(val):
            if val is None:
                return ''
            try:
                return val.strftime('%Y-%m-%d %H:%M:%S')
            except AttributeError:
                return str(val)[:19]

        data = []
        for row in rows:
            item = dict(zip(columns, row))
            raw_password = item.get('password') or ''
            data.append({
                'id': item.get('id'),
                'name': item.get('Nombres') or '',
                'email': item.get('correo') or '',
                'unes': item.get('unes') or '',
                # Nunca se envía el hash ni la contraseña al frontend.
                # Solo el flag booleano para que la UI sepa si hay valor.
                'has_password': bool(str(raw_password).strip()),
                'password_is_hashed': es_password_hash(raw_password),
                'cargo': item.get('cargo') or '',
                'Activo': bool(item.get('Activo')) if item.get('Activo') is not None else False,
                'FechaCreacion': fmt_date(item.get('FechaCreacion')),
            })
        cursor.close()
        conn.close()
        return jsonify({'ok': True, 'data': data}), 200
    except Exception as e:
        print(f"Error en get_usuarios: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

@app.route('/update_usuario/<int:id>', methods=['PUT', 'POST'])
def update_usuario(id):
    """Actualiza un usuario existente en vacacionesgyj.dbo.users."""
    conn = get_db_connection2()
    if not conn:
        return jsonify({'ok': False, 'error': 'No se pudo conectar a vacacionesgyj'}), 500
    
    try:
        payload = request.get_json(silent=True) or {}
        
        nombre = payload.get('nombre')
        correo = payload.get('correo')
        cargo = payload.get('cargo')
        unes = payload.get('unes')
        password = payload.get('password')
        activo = payload.get('activo', True)
        
        if not nombre or not correo:
            return jsonify({'ok': False, 'error': 'El nombre y el correo son obligatorios'}), 400
        
        cursor = conn.cursor()
        
        # Verificar si el usuario existe
        cursor.execute("SELECT 1 FROM users WHERE id = ?", (id,))
        if not cursor.fetchone():
            cursor.close()
            return jsonify({'ok': False, 'error': 'Usuario no encontrado'}), 404
        
        # Verificar si ya existe otro usuario con el mismo correo (excluyendo el actual)
        cursor.execute("SELECT 1 FROM users WHERE correo = ? AND id != ?", (correo, id))
        if cursor.fetchone():
            cursor.close()
            return jsonify({'ok': False, 'error': 'Ya existe un usuario con ese correo'}), 409
        
        # Generar hash de contraseña si se proporcionó una nueva
        password_hash = None
        if password:
            password_hash = generate_password_hash(password)
        
        # Construir query de actualización dinámicamente
        update_fields = []
        update_values = []
        
        if nombre:
            update_fields.append("Nombres = ?")
            update_values.append(nombre)
        
        if correo:
            update_fields.append("correo = ?")
            update_values.append(correo)
        
        if cargo is not None:
            update_fields.append("cargo = ?")
            update_values.append(cargo)
        
        if unes is not None:
            update_fields.append("unes = ?")
            update_values.append(unes)
        
        if password_hash:
            update_fields.append("password = ?")
            update_values.append(password_hash)
        
        if activo is not None:
            update_fields.append("Activo = ?")
            update_values.append(1 if activo else 0)
        
        if not update_fields or len(update_fields) == 0:
            cursor.close()
            return jsonify({'ok': False, 'error': 'No hay campos para actualizar'}), 400
        
        # Agregar ID al final de los valores
        update_values.append(id)
        
        query = f"UPDATE users SET {', '.join(update_fields)} WHERE id = ?"
        
        cursor.execute(query, update_values)
        conn.commit()
        cursor.close()
        
        return jsonify({'ok': True, 'message': 'Usuario actualizado correctamente'}), 200
    except Exception as e:
        print(f"Error en update_usuario: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

@app.route('/delete_usuario/<int:id>', methods=['DELETE'])
def delete_usuario(id):
    """Elimina un usuario de vacacionesgyj.dbo.users."""
    conn = get_db_connection2()
    if not conn:
        return jsonify({'ok': False, 'error': 'No se pudo conectar a vacacionesgyj'}), 500
    
    try:
        cursor = conn.cursor()
        
        # Verificar si el usuario existe antes de eliminarlo
        cursor.execute("SELECT 1 FROM users WHERE id = ?", (id,))
        if not cursor.fetchone():
            cursor.close()
            return jsonify({'ok': False, 'error': 'Usuario no encontrado'}), 404
        
        # Eliminar el usuario
        cursor.execute("DELETE FROM users WHERE id = ?", (id,))
        conn.commit()
        cursor.close()
        
        return jsonify({'ok': True, 'message': 'Usuario eliminado correctamente'}), 200
    except Exception as e:
        print(f"Error en delete_usuario: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

# Ruta del archivo que mapea cada correo (jefe de filial) con las cédulas de su equipo.
FILIAL_JSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data filial', 'filial.json')


def normalizar_cedula(valor):
    """Normaliza una cédula a texto sin decimales ni espacios para poder compararlas."""
    if valor is None:
        return ''
    texto = str(valor).strip()
    if '.' in texto:
        texto = texto.split('.')[0]
    return texto.strip()


def obtener_cedulas_filial(correo):
    """
    Lee 'backend/data filial/filial.json' y devuelve el conjunto de cédulas (texto)
    asociadas al correo consultado.

    Retorna:
        - set con las cédulas permitidas cuando el correo existe en el JSON.
        - None cuando el correo no está en el JSON o no se pudo leer el archivo
          (en ese caso el endpoint NO aplica filtro para no romper la vista).
    """
    if not correo:
        return None
    try:
        if not os.path.isfile(FILIAL_JSON_PATH):
            print(f"filial.json no encontrado en: {FILIAL_JSON_PATH}")
            return None

        with open(FILIAL_JSON_PATH, 'r', encoding='utf-8') as archivo:
            filial_data = json.load(archivo)

        if not isinstance(filial_data, dict):
            print("filial.json no tiene la estructura esperada (diccionario).")
            return None

        correo_key = str(correo).strip().lower()
        registros = None
        for llave, valor in filial_data.items():
            if str(llave).strip().lower() == correo_key:
                registros = valor
                break

        if registros is None:
            print(f"Correo {correo_key} no encontrado en filial.json")
            return None

        cedulas = set()
        for item in registros or []:
            if isinstance(item, dict):
                cedula = normalizar_cedula(item.get('cedula'))
            else:
                cedula = normalizar_cedula(item)
            if cedula:
                cedulas.add(cedula)
        return cedulas
    except Exception as e:
        print(f"Error leyendo filial.json: {e}")
        return None


@app.route('/pbi-colaborador-vacaciones', methods=['GET'])
def get_pbi_colaborador_vacaciones():
    """Devuelve la información de BD_Integraciones.dbo.PBI_Colaborador_Vacaciones como API, fusionada con inf_asignacion.

    Parámetros opcionales de la petición:
        - unes: código UNES de 3 dígitos. Si se envía sin 'correo', se usa para
          validar su existencia (flujo de Login).
        - correo: correo del usuario logueado. Cuando UNES = 106, se usa para
          filtrar la lista por las cédulas de su filial definidas en filial.json.
    """

    unes_query = request.args.get('unes', default=None, type=str)
    correo_query = (request.args.get('correo', default=None, type=str) or '').strip()

    conn1 = get_db_connection()
    if not conn1:
        return jsonify({'ok': False, 'error': 'No se pudo conectar a BD_Integraciones'}), 500

    try:
        # Validación de existencia de UNES (flujo de Login: solo envía 'unes').
        # Cuando llega 'correo', la petición corresponde al listado de Home y no debe
        # caer en esta rama, para poder devolver el arreglo completo/filtrado.
        if unes_query is not None and not correo_query:
            if not unes_query.isdigit():
                return jsonify({'ok': False, 'error': 'La UNES debe contener solo números'}), 400
            if len(unes_query) != 3:
                return jsonify({'ok': False, 'error': 'La UNES debe tener exactamente 3 dígitos'}), 400

            unes_value = unes_query[-3:]
            cursor1 = conn1.cursor()
            query1 = (
                "SELECT TOP 1 IDCia_CO FROM BD_Integraciones.dbo.PBI_Colaborador_Vacaciones "
                "WHERE RIGHT('000' + CAST(ISNULL(CAST(IDCia_CO AS VARCHAR), '') AS VARCHAR(20)), 3) = ?"
            )
            cursor1.execute(query1, (unes_value,))
            row = cursor1.fetchone()
            conn1.close()
            if row is None:
                return jsonify({'ok': True, 'exists': False, 'unes': unes_value}), 200
            return jsonify({'ok': True, 'exists': True, 'unes': unes_value, 'idcia': row[0]}), 200

        limit = request.args.get('limit', default=100, type=int)
        if limit is None:
            limit = 100
        limit = max(1, min(limit, 1200))

        cursor1 = conn1.cursor()
        query1 = f"SELECT TOP {limit} * FROM BD_Integraciones.dbo.PBI_Colaborador_Vacaciones"
        cursor1.execute(query1)
        rows1 = cursor1.fetchall()
        columns1 = [col[0] for col in (cursor1.description or [])]

        def serialize(value):
            if value is None:
                return None
            try:
                import decimal
                if isinstance(value, decimal.Decimal):
                    return float(value)
            except Exception:
                pass
            try:
                return value.isoformat()
            except Exception:
                return str(value)

        data = []
        for row in rows1:
            item = {}
            for i, col in enumerate(columns1):
                item[col] = serialize(row[i])
            data.append(item)
        
        cursor1.close()
        conn1.close()

        # 2. Obtener asignaciones de BD2
        asignaciones = {}
        conn2 = get_db_connection2()
        if conn2:
            try:
                cursor2 = conn2.cursor()
                cursor2.execute("SELECT * FROM inf_asignacion")
                rows2 = cursor2.fetchall()
                columns2 = [col[0] for col in (cursor2.description or [])]
                
                for row in rows2:
                    asig_item = {}
                    for i, col in enumerate(columns2):
                        asig_item[col] = row[i]
                    
                    ident = asig_item.get('identificacion')
                    if ident:
                        asignaciones[str(ident)] = asig_item
                cursor2.close()
                conn2.close()
            except Exception as e:
                print(f"Error al obtener asignaciones de BD2: {e}")

        # 3. Fusionar datos
        def format_date(val):
            if not val:
                return ''
            try:
                return val.strftime('%Y-%m-%d')
            except AttributeError:
                return str(val)[:10]

        for emp in data:
            cedula_str = str(emp.get('cedula', ''))
            if cedula_str in asignaciones:
                match = asignaciones[cedula_str]
                emp['estado'] = match.get('estado_asignacion') or 'pendiente'
                emp['totalDiasTomados'] = match.get('total_dias_empleado') or 0
                emp['observaciones'] = match.get('observaciones') or ''
                emp['fechaIngreso'] = format_date(match.get('fecha_regreso'))
                emp['diaFamilia1'] = format_date(match.get('dia_familia1'))
                emp['diaFamilia2'] = format_date(match.get('dia_familia2'))
                emp['motivoRechazo'] = match.get('motivo_rechazo') or ''
                emp['th_asignacion'] = match.get('th_asignacion') or ''
                
                emp['periodos'] = [
                    {
                        'inicio': format_date(match.get('periodo1_fecha1')),
                        'fin': format_date(match.get('periodo1_fecha2')),
                        'dias': match.get('periodo1_dias1') or 0
                    },
                    {
                        'inicio': format_date(match.get('periodo2_fecha1')),
                        'fin': format_date(match.get('periodo2_fecha2')),
                        'dias': match.get('periodo2_dias2') or 0
                    },
                    {
                        'inicio': format_date(match.get('periodo3_fecha1')),
                        'fin': format_date(match.get('periodo3_fecha2')),
                        'dias': match.get('periodo3_dias3') or 0
                    }
                ]
            else:
                emp['estado'] = 'pendiente'
                emp['totalDiasTomados'] = 0
                emp['observaciones'] = ''
                emp['fechaIngreso'] = ''
                emp['diaFamilia1'] = ''
                emp['diaFamilia2'] = ''
                emp['motivoRechazo'] = ''
                emp['periodos'] = [
                    {'inicio': '', 'fin': '', 'dias': 0},
                    {'inicio': '', 'fin': '', 'dias': 0},
                    {'inicio': '', 'fin': '', 'dias': 0}
                ]

        # 4. Filtrado por filial (solo aplica cuando UNES = 106 y se recibió el correo).
        unes_normalizada = ''.join(ch for ch in str(unes_query or '') if ch.isdigit())[-3:] if unes_query else ''
        if unes_normalizada == '106' and correo_query:
            cedulas_permitidas = obtener_cedulas_filial(correo_query)
            if cedulas_permitidas is not None:
                data = [
                    emp for emp in data
                    if normalizar_cedula(emp.get('cedula')) in cedulas_permitidas
                ]
                print(f"Filtro filial aplicado para {correo_query}: {len(data)} colaboradores")

        return jsonify({'ok': True, 'count': len(data), 'data': data}), 200
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/registrar_data', methods=['POST'])
def registrar_data():
    conn = get_db_connection2()
    if not conn:
        return jsonify({'ok': False, 'error': 'No se pudo conectar a vacacionesgyj'}), 500
    try:
        data = request.get_json() or {}
        
        identificacion = data.get('identificacion')
        empleado = data.get('empleado')
        cargo = data.get('cargo')
        desc_unes = data.get('desc_unes')
        unes = data.get('unes')
        correo = data.get('correo')
        estado_asignacion = data.get('estado_asignacion', 'pendiente')
        dias_a_corte = data.get('dias_a_corte', 0)
        observaciones = data.get('observaciones')
        motivo_rechazo = data.get('motivo_rechazo')
        
        periodo1_fecha1 = data.get('periodo1_fecha1')
        periodo1_fecha2 = data.get('periodo1_fecha2')
        periodo1_dias1 = data.get('periodo1_dias1', 0)
        
        periodo2_fecha1 = data.get('periodo2_fecha1')
        periodo2_fecha2 = data.get('periodo2_fecha2')
        periodo2_dias2 = data.get('periodo2_dias2', 0)
        
        periodo3_fecha1 = data.get('periodo3_fecha1')
        periodo3_fecha2 = data.get('periodo3_fecha2')
        periodo3_dias3 = data.get('periodo3_dias3', 0)
        
        fecha_regreso = data.get('fecha_regreso')
        total_dias_empleado = data.get('total_dias_empleado', 0)

        # Convert empty strings to None (NULL in SQL Server)
        def to_db_val(val, is_number=False):
            if val == '' or val is None:
                return None
            if is_number:
                try:
                    return int(val)
                except ValueError:
                    try:
                        return float(val)
                    except ValueError:
                        return 0
            return val

        identificacion = to_db_val(identificacion, is_number=True)
        dias_a_corte = to_db_val(dias_a_corte, is_number=True)
        periodo1_dias1 = to_db_val(periodo1_dias1, is_number=True)
        periodo2_dias2 = to_db_val(periodo2_dias2, is_number=True)
        periodo3_dias3 = to_db_val(periodo3_dias3, is_number=True)
        total_dias_empleado = to_db_val(total_dias_empleado, is_number=True)

        periodo1_fecha1 = to_db_val(periodo1_fecha1)
        periodo1_fecha2 = to_db_val(periodo1_fecha2)
        periodo2_fecha1 = to_db_val(periodo2_fecha1)
        periodo2_fecha2 = to_db_val(periodo2_fecha2)
        periodo3_fecha1 = to_db_val(periodo3_fecha1)
        periodo3_fecha2 = to_db_val(periodo3_fecha2)
        fecha_regreso = to_db_val(fecha_regreso)
        motivo_rechazo = to_db_val(motivo_rechazo)
        
        # New field: th_asignacion (Talento Humano who approved/rejected)
        th_asignacion = to_db_val(data.get('th_asignacion'))

        cursor = conn.cursor()
        
        # Check if record already exists
        cursor.execute("SELECT 1 FROM inf_asignacion WHERE identificacion = ?", (identificacion,))
        exists = cursor.fetchone()
        
        if exists:
            query = """
                UPDATE inf_asignacion
                SET empleado = ?,
                    cargo = ?,
                    desc_unes = ?,
                    unes = ?,
                    correo = ?,
                    estado_asignacion = ?,
                    dias_a_corte = ?,
                    observaciones = ?,
                    motivo_rechazo = ?,
                    th_asignacion = ?,
                    periodo1_fecha1 = ?,
                    periodo1_fecha2 = ?,
                    periodo1_dias1 = ?,
                    periodo2_fecha1 = ?,
                    periodo2_fecha2 = ?,
                    periodo2_dias2 = ?,
                    periodo3_fecha1 = ?,
                    periodo3_fecha2 = ?,
                    periodo3_dias3 = ?,
                    fecha_regreso = ?,
                    total_dias_empleado = ?,
                    fecha_update = GETDATE()
                WHERE identificacion = ?
            """
            cursor.execute(query, (
                empleado, cargo, desc_unes, unes, correo, estado_asignacion,
                dias_a_corte, observaciones, motivo_rechazo, th_asignacion,
                periodo1_fecha1, periodo1_fecha2, periodo1_dias1,
                periodo2_fecha1, periodo2_fecha2, periodo2_dias2,
                periodo3_fecha1, periodo3_fecha2, periodo3_dias3,
                fecha_regreso, total_dias_empleado, identificacion
            ))
        else:
            query = """
                INSERT INTO inf_asignacion
                (
                    identificacion, empleado, cargo, desc_unes, unes, correo, estado_asignacion,
                    dias_a_corte, observaciones, motivo_rechazo, th_asignacion,
                    periodo1_fecha1, periodo1_fecha2, periodo1_dias1,
                    periodo2_fecha1, periodo2_fecha2, periodo2_dias2,
                    periodo3_fecha1, periodo3_fecha2, periodo3_dias3,
                    fecha_regreso, total_dias_empleado,
                    fecha_registro
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
            """
            cursor.execute(query, (
                identificacion, empleado, cargo, desc_unes, unes, correo, estado_asignacion,
                dias_a_corte, observaciones, motivo_rechazo, th_asignacion,
                periodo1_fecha1, periodo1_fecha2, periodo1_dias1,
                periodo2_fecha1, periodo2_fecha2, periodo2_dias2,
                periodo3_fecha1, periodo3_fecha2, periodo3_dias3,
                fecha_regreso, total_dias_empleado
            ))
            
        conn.commit()
        return jsonify({'ok': True, 'message': 'Datos registrados correctamente'}), 200
    except Exception as e:
        print(f"Error en registrar_data: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

@app.route('/ver_data/<int:identificacion>', methods=['GET'])
def ver_data(identificacion):
    conn = get_db_connection2()
    if not conn:
        return jsonify({'ok': False, 'error': 'No se pudo conectar a vacacionesgyj'}), 500
    try:
        cursor1 = conn.cursor()
        # Solo columnas relevantes (para el nuevo modal de edición)
        query1 = """
            SELECT
                identificacion,
                empleado,
                cargo,
                desc_unes,
                unes,
                correo,
                estado_asignacion,
                dias_a_corte,
                observaciones,
                motivo_rechazo,
                th_asignacion,
                dia_familia1,
                dia_familia2,
                periodo1_fecha1,
                periodo1_fecha2,
                periodo1_dias1,
                periodo2_fecha1,
                periodo2_fecha2,
                periodo2_dias2,
                periodo3_fecha1,
                periodo3_fecha2,
                periodo3_dias3,
                fecha_regreso,
                total_dias_empleado,
                fecha_registro,
                fecha_update
            FROM inf_asignacion
            WHERE identificacion = ?
        """
        cursor1.execute(query1, (identificacion,))
        rows1 = cursor1.fetchall()
        columns1 = [col[0] for col in (cursor1.description or [])]

        def format_date(val):
            if val is None or val == '':
                return ''
            try:
                return val.strftime('%Y-%m-%d')
            except AttributeError:
                # Si ya viene como string
                return str(val)[:10]

        def format_datetime(val):
            if val is None or val == '':
                return ''
            try:
                return val.strftime('%Y-%m-%d %H:%M:%S')
            except AttributeError:
                return str(val)[:19]

        data = []
        for row in rows1:
            emp = dict(zip(columns1, row))

            # Campos estrictamente pedidos
            emp['dias_a_corte'] = float(emp.get('dias_a_corte') or 0)
            emp['total_dias_empleado'] = float(emp.get('total_dias_empleado') or 0)
            emp['observaciones'] = emp.get('observaciones') or ''
            emp['motivoRechazo'] = emp.get('motivo_rechazo') or ''
            emp['th_asignacion'] = emp.get('th_asignacion') or ''

            emp['periodo1_fecha1'] = format_date(emp.get('periodo1_fecha1'))
            emp['periodo1_fecha2'] = format_date(emp.get('periodo1_fecha2'))
            emp['periodo2_fecha1'] = format_date(emp.get('periodo2_fecha1'))
            emp['periodo2_fecha2'] = format_date(emp.get('periodo2_fecha2'))
            emp['periodo3_fecha1'] = format_date(emp.get('periodo3_fecha1'))
            emp['periodo3_fecha2'] = format_date(emp.get('periodo3_fecha2'))
            emp['fecha_regreso'] = format_date(emp.get('fecha_regreso'))

            # Campos usados por la UI de asignación
            emp['diaFamilia1'] = format_date(emp.get('dia_familia1'))
            emp['diaFamilia2'] = format_date(emp.get('dia_familia2'))

            emp['fecha_registro'] = format_datetime(emp.get('fecha_registro'))
            emp['fecha_update'] = format_datetime(emp.get('fecha_update'))

            # Alias/estructura para reutilizar la UI actual (periodos + nombres usados en Home.jsx)
            emp['estado'] = emp.get('estado_asignacion') or 'pendiente'
            emp['totalDiasTomados'] = emp.get('total_dias_empleado') or 0
            emp['fechaIngreso'] = emp.get('fecha_regreso')
            emp['periodos'] = [
                {
                    'inicio': emp.get('periodo1_fecha1'),
                    'fin': emp.get('periodo1_fecha2'),
                    'dias': emp.get('periodo1_dias1') or 0
                },
                {
                    'inicio': emp.get('periodo2_fecha1'),
                    'fin': emp.get('periodo2_fecha2'),
                    'dias': emp.get('periodo2_dias2') or 0
                },
                {
                    'inicio': emp.get('periodo3_fecha1'),
                    'fin': emp.get('periodo3_fecha2'),
                    'dias': emp.get('periodo3_dias3') or 0
                }
            ]

            data.append(emp)

        return jsonify({'ok': True, 'data': data}), 200
    except Exception as e:
        print(f"Error en registrar_data: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

@app.route('/actualizar_data/<int:identificacion>', methods=['PUT'])
def actualizar_data(identificacion):
    conn = get_db_connection2()
    if not conn:
        return jsonify({'ok': False, 'error': 'No se pudo conectar a vacacionesgyj'}), 500

    try:
        payload = request.get_json() or {}

        empleado = payload.get('empleado')
        cargo = payload.get('cargo')
        desc_unes = payload.get('desc_unes')
        unes = payload.get('unes')
        correo = payload.get('correo')
        estado_asignacion = payload.get('estado_asignacion', 'pendiente')
        dias_a_corte = payload.get('dias_a_corte', 0)
        observaciones = payload.get('observaciones')

        periodo1_fecha1 = payload.get('periodo1_fecha1')
        periodo1_fecha2 = payload.get('periodo1_fecha2')
        periodo1_dias1 = payload.get('periodo1_dias1', 0)

        periodo2_fecha1 = payload.get('periodo2_fecha1')
        periodo2_fecha2 = payload.get('periodo2_fecha2')
        periodo2_dias2 = payload.get('periodo2_dias2', 0)

        periodo3_fecha1 = payload.get('periodo3_fecha1')
        periodo3_fecha2 = payload.get('periodo3_fecha2')
        periodo3_dias3 = payload.get('periodo3_dias3', 0)

        fecha_regreso = payload.get('fecha_regreso')
        dia_familia1 = payload.get('dia_familia1')
        dia_familia2 = payload.get('dia_familia2')
        total_dias_empleado = payload.get('total_dias_empleado', 0)
        motivo_rechazo = payload.get('motivo_rechazo')

        def to_db_val(val, is_number=False):
            if val == '' or val is None:
                return None
            if is_number:
                try:
                    return int(val)
                except ValueError:
                    try:
                        return float(val)
                    except ValueError:
                        return 0
            return val

        dias_a_corte = to_db_val(dias_a_corte, is_number=True)
        periodo1_dias1 = to_db_val(periodo1_dias1, is_number=True)
        periodo2_dias2 = to_db_val(periodo2_dias2, is_number=True)
        periodo3_dias3 = to_db_val(periodo3_dias3, is_number=True)
        total_dias_empleado = to_db_val(total_dias_empleado, is_number=True)

        periodo1_fecha1 = to_db_val(periodo1_fecha1)
        periodo1_fecha2 = to_db_val(periodo1_fecha2)
        periodo2_fecha1 = to_db_val(periodo2_fecha1)
        periodo2_fecha2 = to_db_val(periodo2_fecha2)
        periodo3_fecha1 = to_db_val(periodo3_fecha1)
        periodo3_fecha2 = to_db_val(periodo3_fecha2)
        fecha_regreso = to_db_val(fecha_regreso)
        dia_familia1 = to_db_val(dia_familia1)
        dia_familia2 = to_db_val(dia_familia2)
        observaciones = to_db_val(observaciones)
        motivo_rechazo = to_db_val(motivo_rechazo)

        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM inf_asignacion WHERE identificacion = ?", (identificacion,))
        exists = cursor.fetchone()
        if not exists:
            return jsonify({'ok': False, 'error': 'Registro no encontrado'}), 404

        query = """
            UPDATE inf_asignacion
            SET empleado = ?,
                cargo = ?,
                desc_unes = ?,
                unes = ?,
                correo = ?,
                estado_asignacion = ?,
                dias_a_corte = ?,
                observaciones = ?,
                periodo1_fecha1 = ?,
                periodo1_fecha2 = ?,
                periodo1_dias1 = ?,
                periodo2_fecha1 = ?,
                periodo2_fecha2 = ?,
                periodo2_dias2 = ?,
                periodo3_fecha1 = ?,
                periodo3_fecha2 = ?,
                periodo3_dias3 = ?,
                fecha_regreso = ?,
                dia_familia1 = ?,
                dia_familia2 = ?,
                total_dias_empleado = ?,
                motivo_rechazo = ?,
                fecha_update = GETDATE()
            WHERE identificacion = ?
        """

        cursor.execute(query, (
            empleado, cargo, desc_unes, unes, correo, estado_asignacion,
            dias_a_corte, observaciones,
            periodo1_fecha1, periodo1_fecha2, periodo1_dias1,
            periodo2_fecha1, periodo2_fecha2, periodo2_dias2,
            periodo3_fecha1, periodo3_fecha2, periodo3_dias3,
            fecha_regreso, dia_familia1, dia_familia2,
            total_dias_empleado, motivo_rechazo,
            identificacion
        ))

        conn.commit()
        return jsonify({'ok': True, 'message': 'Datos actualizados correctamente'}), 200
    except Exception as e:
        print(f"Error en actualizar_data: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

# Estados de asignación gestionados desde la vista Home.
ESTADO_APROBADO = 'aprobado'
ESTADO_NO_APROBADO = 'no aprobado'


def aprobar_rechazar_asignacion(identificacion, estado, motivo_rechazo=None, th_asignacion=None):
    """
    Actualiza el estado de una asignación en vacacionesgyj.dbo.inf_asignacion.

    - 'aprobado'    -> al pulsar Aprobar en la vista Home.
    - 'no aprobado' -> al pulsar Rechazar; guarda además el motivo del rechazo
      en la columna motivo_rechazo.

    Solo modifica estado_asignacion, motivo_rechazo, th_asignacion y fecha_update,
    de modo que NO sobrescribe las fechas ni los días ya asignados.

    Devuelve una tupla (ok: bool, mensaje: str).
    """
    if estado not in (ESTADO_APROBADO, ESTADO_NO_APROBADO):
        return False, "El estado debe ser 'aprobado' o 'no aprobado'"

    conn = get_db_connection2()
    if not conn:
        return False, 'No se pudo conectar a vacacionesgyj'

    try:
        cursor = conn.cursor()

        # Verificar que la asignación exista antes de actualizar.
        cursor.execute(
            "SELECT 1 FROM inf_asignacion WHERE identificacion = ?",
            (identificacion,)
        )
        if not cursor.fetchone():
            return False, 'Registro de asignación no encontrado'

        if estado == ESTADO_NO_APROBADO:
            motivo = (motivo_rechazo or '').strip()
            if not motivo:
                return False, 'Debe ingresar un motivo para el rechazo'
        else:
            # Al aprobar se limpia cualquier motivo de rechazo previo.
            motivo = None

        cursor.execute("""
            UPDATE inf_asignacion
            SET estado_asignacion = ?,
                motivo_rechazo = ?,
                th_asignacion = ?,
                fecha_update = GETDATE()
            WHERE identificacion = ?
        """, (estado, motivo, th_asignacion, identificacion))

        conn.commit()
        return True, 'Estado de la asignación actualizado correctamente'
    except Exception as e:
        print(f"Error en aprobar_rechazar_asignacion: {e}")
        return False, str(e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


@app.route('/aprobar_rechazar_asignacion', methods=['POST'])
def handle_aprobar_rechazar_asignacion():
    """
    Aprueba o rechaza una asignación de vacaciones.

    Cuerpo esperado (JSON):
        {
            "identificacion": 123456,
            "estado": "aprobado" | "no aprobado",
            "motivo_rechazo": "texto (obligatorio al rechazar)",
            "th_asignacion": "Nombre del gestor de Talento Humano"
        }
    """
    data = request.get_json(silent=True) or {}

    identificacion = data.get('identificacion')
    estado_recibido = str(
        data.get('estado') or data.get('estado_asignacion') or ''
    ).strip().lower()
    motivo_rechazo = data.get('motivo_rechazo') or data.get('motivoRechazo') or ''
    th_asignacion = data.get('th_asignacion')

    if identificacion is None or str(identificacion).strip() == '':
        return jsonify({'ok': False, 'error': 'La identificación es obligatoria'}), 400

    try:
        identificacion = int(float(identificacion))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'La identificación debe ser numérica'}), 400

    # Normaliza el estado recibido (acepta también el vocabulario legado 'rechazada').
    if estado_recibido in ('aprobado', 'aprobada'):
        estado = ESTADO_APROBADO
    elif estado_recibido in ('no aprobado', 'no aprobada', 'rechazado', 'rechazada'):
        estado = ESTADO_NO_APROBADO
    else:
        return jsonify({'ok': False, 'error': "El estado debe ser 'aprobado' o 'no aprobado'"}), 400

    ok, mensaje = aprobar_rechazar_asignacion(
        identificacion, estado, motivo_rechazo, th_asignacion
    )
    if not ok:
        status = 404 if 'no encontrado' in mensaje.lower() else 400
        return jsonify({'ok': False, 'error': mensaje}), status

    return jsonify({'ok': True, 'message': mensaje, 'estado': estado}), 200


@app.route('/obtener_data/<string:unes>', methods=['GET'])
def obtener_data(unes):
    conn = get_db_connection2()
    if not conn:
        return jsonify({'ok': False, 'error': 'No se pudo conectar a vacacionesgyj'}), 500
    try:
        cursor = conn.cursor()
        query = "SELECT * FROM inf_asignacion WHERE unes = ?"
        cursor.execute(query, (unes,))
        rows = cursor.fetchall()
        if not rows:
            return jsonify({'ok': False, 'error': 'Registro no encontrado'}), 404
        columns = [col[0] for col in (cursor.description or [])]
        data = {item['identificacion']: item for item in [dict(zip(columns, row)) for row in rows]}
        return jsonify({'ok': True, 'data': data}), 200
    except Exception as e:
        print(f"Error en obtener_data: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500
    finally:
        try:
            conn.close()
        except Exception:
            pass

def generar_pdf_reporte_vacaciones(employees, unes_filter, desc_unes):
    """
    Genera un PDF con formato vacaciones segun la plantilla institucional
    (basada en el archivo 2-106 PETROLEOS.pdf).
    Cumple la especificacion:
      - A4 horizontal (landscape), margen 6mm
      - 23 columnas con porcentajes exactos del HTML de referencia
      - Super-encabezados verdes (#00B050) y azul (#0070C0) con colspans
      - Estilo CSS equivalente: nowrap para cedulas/fechas/totales, zebra en filas,
        tabla fixed-layout
      - Formulas: Total Tomados = P1 + P2 + P3; Saldo Final = 0 si Total=0, sino
        Pendientes - Total
    Retorna los bytes del PDF generado.
    """
    import io
    from datetime import datetime
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    buffer = io.BytesIO()

    # Pagina A4 horizontal con margen 6mm
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=6 * mm,
        rightMargin=6 * mm,
        topMargin=6 * mm,
        bottomMargin=6 * mm,
        title='Reporte Vacaciones',
        author='GYJ'
    )

    styles = getSampleStyleSheet()

    # Estilo del titulo del reporte
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Title'],
        fontSize=11,
        textColor=colors.HexColor('#003366'),
        alignment=TA_CENTER,
        spaceAfter=2,
        fontName='Helvetica-Bold',
        leading=13
    )
    subtitle_style = ParagraphStyle(
        'SubtitleStyle',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.HexColor('#003366'),
        alignment=TA_CENTER,
        spaceAfter=4,
        fontName='Helvetica-Bold',
        leading=9
    )

    # Fila 1: super-encabezados (header-green / header-blue)
    super_green_style = ParagraphStyle(
        'SuperGreen',
        parent=styles['Normal'],
        fontSize=6.5,
        textColor=colors.white,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        leading=8
    )
    super_blue_style = ParagraphStyle(
        'SuperBlue',
        parent=styles['Normal'],
        fontSize=7.5,
        textColor=colors.white,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        leading=9
    )

    # Fila 2: encabezados de columna (header-blue) - fontSize 6pt
    col_header_style = ParagraphStyle(
        'ColHeader',
        parent=styles['Normal'],
        fontSize=6,
        textColor=colors.white,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold',
        leading=7
    )

    # Celdas de datos
    cell_nowrap_style = ParagraphStyle(
        'CellNoWrap',
        parent=styles['Normal'],
        fontSize=6.2,
        textColor=colors.black,
        alignment=TA_CENTER,
        fontName='Helvetica',
        leading=7.5,
        wordWrap='CJK'
    )
    cell_nowrap_total_style = ParagraphStyle(
        'CellNoWrapTotal',
        parent=cell_nowrap_style,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#003366')
    )
    cell_left_style = ParagraphStyle(
        'CellLeft',
        parent=cell_nowrap_style,
        alignment=TA_LEFT
    )

    # -----------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------
    def html_escape(val):
        if val is None:
            return ''
        s = str(val)
        return (s.replace('&', '&amp;')
                 .replace('<', '&lt;')
                 .replace('>', '&gt;'))

    def fmt_date(val):
        if val is None or val == '':
            return ''
        try:
            if hasattr(val, 'strftime'):
                return val.strftime('%Y-%m-%d')
            s = str(val)
            if len(s) >= 10 and s[4:5] == '-':
                return s[:10]
            return s
        except Exception:
            return str(val) if val else ''

    def safe_num(val, default=0):
        if val is None or val == '':
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def fmt_num(val):
        n = safe_num(val)
        if n == 0:
            return '0'
        if n == int(n):
            return str(int(n))
        return f'{n:g}'

    # -----------------------------------------------------------------
    # Titulo fuera de la tabla
    # -----------------------------------------------------------------
    elements = []
    unes_label = unes_filter or 'TODAS'
    desc_label = desc_unes or ''
    titulo = f"FORMATO VACACIONES - UNES {unes_label}"
    if desc_label:
        titulo += f" ({desc_label})"
    elements.append(Paragraph(titulo, title_style))
    elements.append(Paragraph(
        f"Fecha de generación: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        subtitle_style
    ))

    # -----------------------------------------------------------------
    # Fila 1: Super-encabezados (23 columnas exactas)
    # -----------------------------------------------------------------
    # Colocamos cada Paragraph en el indice exacto donde arranca su respectivo SPAN:
    # Col 0 (A1..G1): 'FORMATO VACACIONES' (Azul)
    # Col 7 (H1..J1): 'PRIMER CORTE...' (Verde)
    # Col 10 (K1..M1): 'SEGUNDO CORTE...' (Verde)
    # Col 13 (N1): '24 DE DICIEMBRE UNES' (Verde)
    # Col 14 (O1..Q1): 'TERCER CORTE...' (Verde)
    # Col 17 (R1): '31 DE DICIEMBRE UNES' (Verde)
    # Col 18..22 (S1..W1): Celdas sin texto / sin fondo

    super_row = [Paragraph('', super_green_style) for _ in range(23)]
    
    super_row[0] = Paragraph('FORMATO VACACIONES', super_blue_style)
    super_row[7] = Paragraph(
        'PRIMER CORTE 28 DE NOVIEMBRE AL 6 DICIEMBRE<br/>FECHA DE PAGO 28 DE NOVIEMBRE',
        super_green_style
    )
    super_row[10] = Paragraph(
        'SEGUNDO CORTE 7 AL 18 DE DICIEMBRE<br/>FECHA DE PAGO 15 DE DICIEMBRE',
        super_green_style
    )
    super_row[13] = Paragraph('24 DE DICIEMBRE UNES', super_green_style)
    super_row[14] = Paragraph(
        'TERCER CORTE 19 DE DICEMBRE AL 12 DE ENERO<br/>FECHA DE PAGO 29 DICIEMBRE',
        super_green_style
    )
    super_row[17] = Paragraph('31 DE DICIEMBRE UNES', super_green_style)

    # -----------------------------------------------------------------
    # Fila 2: Encabezados de columna
    # -----------------------------------------------------------------
    column_headers = [
        'CEDULA',
        'APELLIDOS Y NOMBRES',
        'CARGO',
        'UNES',
        'FECHA DE INGRESO',
        'Correo personal de la persona (notificacion)',
        'DIAS PENDIENTES DE VACACIONES',
        'FECHA DE INICIO DE VACACIONES',
        'FECHA FIN DE VACACIONES',
        'TOTAL DÍAS',
        'FECHA DE INICIO DE VACACIONES2',
        'FECHA DE TERMINACIÓN DE VACACIONES',
        'TOTAL DÍAS3',
        'DIA DE LA FAMILIA',
        'FECHA DE INICIO DE VACACIONES4',
        'FECHA DE TERMINACIÓN DE VACACIONES5',
        'TOTAL DÍAS6',
        'DÍA DE LA FAMILIA 7',
        'TOTAL DIAS TOMADOS',
        'SALDO FINAL A 30 ENERO',
        'FECHA DE INGRESO LABORAL (REGRESO A TU LUGAR DE TRABAJO)',
        'OBSERVACIONES',
        'FIRMA',
    ]
    col_row = [Paragraph(html_escape(h).replace('\n', '<br/>'), col_header_style)
               for h in column_headers]

    # -----------------------------------------------------------------
    # Anchos de columna
    # -----------------------------------------------------------------
    col_pct = [
        6.1, 12.5, 10.0, 3.5, 5.5, 9.0, 4.0,
        5.0, 5.0, 3.0,
        5.0, 5.0, 3.0,
        4.5,
        5.0, 5.0, 3.0,
        4.5,
        3.5, 3.5, 5.5, 8.0, 4.0
    ]
    total_pct = sum(col_pct)
    usable_w_pt = (297.0 - 12.0) / 25.4 * 72.0
    col_widths = [round(usable_w_pt * p / total_pct, 2) for p in col_pct]

    # -----------------------------------------------------------------
    # Filas de datos
    # -----------------------------------------------------------------
    rows = [super_row, col_row]

    for emp in employees:
        cedula = str(emp.get('cedula', '') or '')
        nombre = str(emp.get('Empleado', '') or '').upper()
        cargo = str(emp.get('Cargo', '') or '').upper()
        unes = str(emp.get('IDCia_CO', '') or '')
        fecha_ingreso = fmt_date(emp.get('fecha_ingreso') or emp.get('Fecha_Ingreso'))
        correo = str(emp.get('email', '') or '').lower()
        dias_pendientes = safe_num(emp.get('dias_vacaciones_corteDic'))

        periodos = emp.get('periodos') or [{}, {}, {}]
        p1 = periodos[0] if len(periodos) > 0 else {}
        p2 = periodos[1] if len(periodos) > 1 else {}
        p3 = periodos[2] if len(periodos) > 2 else {}

        p1_ini = fmt_date(p1.get('inicio'))
        p1_fin = fmt_date(p1.get('fin'))
        p1_dias = safe_num(p1.get('dias'))

        p2_ini = fmt_date(p2.get('inicio'))
        p2_fin = fmt_date(p2.get('fin'))
        p2_dias = safe_num(p2.get('dias'))
        dia_fam1 = fmt_date(emp.get('diaFamilia1'))

        p3_ini = fmt_date(p3.get('inicio'))
        p3_fin = fmt_date(p3.get('fin'))
        p3_dias = safe_num(p3.get('dias'))
        dia_fam2 = fmt_date(emp.get('diaFamilia2'))

        total_tomados = p1_dias + p2_dias + p3_dias
        saldo_final = 0 if total_tomados == 0 else (dias_pendientes - total_tomados)

        fecha_regreso = fmt_date(emp.get('fechaIngreso') or emp.get('fecha_regreso'))
        observaciones = str(emp.get('observaciones', '') or '')

        row = [
            Paragraph(html_escape(cedula), cell_nowrap_style),
            Paragraph(html_escape(nombre), cell_left_style),
            Paragraph(html_escape(cargo), cell_left_style),
            Paragraph(html_escape(unes), cell_nowrap_style),
            Paragraph(html_escape(fecha_ingreso), cell_nowrap_style),
            Paragraph(html_escape(correo), cell_left_style),
            Paragraph(fmt_num(dias_pendientes), cell_nowrap_style),
            Paragraph(html_escape(p1_ini), cell_nowrap_style),
            Paragraph(html_escape(p1_fin), cell_nowrap_style),
            Paragraph(fmt_num(p1_dias), cell_nowrap_style),
            Paragraph(html_escape(p2_ini), cell_nowrap_style),
            Paragraph(html_escape(p2_fin), cell_nowrap_style),
            Paragraph(fmt_num(p2_dias), cell_nowrap_style),
            Paragraph(html_escape(dia_fam1), cell_nowrap_style),
            Paragraph(html_escape(p3_ini), cell_nowrap_style),
            Paragraph(html_escape(p3_fin), cell_nowrap_style),
            Paragraph(fmt_num(p3_dias), cell_nowrap_style),
            Paragraph(html_escape(dia_fam2), cell_nowrap_style),
            Paragraph(fmt_num(total_tomados), cell_nowrap_total_style),
            Paragraph(fmt_num(saldo_final), cell_nowrap_total_style),
            Paragraph(html_escape(fecha_regreso), cell_nowrap_style),
            Paragraph(html_escape(observaciones), cell_left_style),
            Paragraph('', cell_nowrap_style),
        ]
        rows.append(row)

    if len(employees) == 0:
        empty_row = [Paragraph('-', cell_nowrap_style)] * 23
        empty_row[1] = Paragraph('Sin datos para mostrar', cell_left_style)
        rows.append(empty_row)

    # -----------------------------------------------------------------
    # Tabla con repeatRows=2
    # -----------------------------------------------------------------
    table = Table(rows, colWidths=col_widths, repeatRows=2)

    colspan_specs = [
        ('SPAN', (0, 0), (6, 0)),    # A:G - FORMATO VACACIONES (Azul)
        ('SPAN', (7, 0), (9, 0)),    # H:J - PRIMER CORTE (Verde)
        ('SPAN', (10, 0), (12, 0)),  # K:M - SEGUNDO CORTE (Verde)
        ('SPAN', (13, 0), (13, 0)),  # N   - 24 DE DICIEMBRE UNES (Verde)
        ('SPAN', (14, 0), (16, 0)),  # O:Q - TERCER CORTE (Verde)
        ('SPAN', (17, 0), (17, 0)),  # R   - 31 DE DICIEMBRE UNES (Verde)
        ('SPAN', (18, 0), (22, 0)),  # S:W - Transparente
    ]

    ts = TableStyle([
        # ---- Fila 0: super-encabezados ----
        ('BACKGROUND', (0, 0), (6, 0), colors.HexColor('#0070C0')),
        ('BACKGROUND', (7, 0), (9, 0), colors.HexColor('#00B050')),
        ('BACKGROUND', (10, 0), (12, 0), colors.HexColor('#00B050')),
        ('BACKGROUND', (13, 0), (13, 0), colors.HexColor('#00B050')),
        ('BACKGROUND', (14, 0), (16, 0), colors.HexColor('#00B050')),
        ('BACKGROUND', (17, 0), (17, 0), colors.HexColor('#00B050')),

        ('TEXTCOLOR', (0, 0), (17, 0), colors.white),
        ('FONTNAME', (0, 0), (17, 0), 'Helvetica-Bold'),
        ('ALIGN', (0, 0), (22, 0), 'CENTER'),
        ('VALIGN', (0, 0), (22, 0), 'MIDDLE'),

        # ---- Fila 1: encabezados de columna (azul) ----
        ('BACKGROUND', (0, 1), (22, 1), colors.HexColor('#0070C0')),
        ('TEXTCOLOR', (0, 1), (22, 1), colors.white),
        ('FONTNAME', (0, 1), (22, 1), 'Helvetica-Bold'),
        ('ALIGN', (0, 1), (22, 1), 'CENTER'),
        ('VALIGN', (0, 1), (22, 1), 'MIDDLE'),

        # ---- Filas de datos ----
        ('VALIGN', (0, 2), (22, -1), 'MIDDLE'),
        ('ALIGN', (0, 2), (22, -1), 'CENTER'),
        ('ALIGN', (1, 2), (1, -1), 'LEFT'),
        ('ALIGN', (2, 2), (2, -1), 'LEFT'),
        ('ALIGN', (5, 2), (5, -1), 'LEFT'),
        ('ALIGN', (21, 2), (21, -1), 'LEFT'),
        ('ROWBACKGROUNDS', (0, 2), (22, -1), [colors.white, colors.HexColor('#F4F7FA')]),
        ('BACKGROUND', (18, 2), (19, -1), colors.HexColor('#EBF3FA')),

        # ---- Bordes y paddings ----
        ('GRID', (0, 0), (22, -1), 0.5, colors.HexColor('#B0C4DE')),
        ('LINEBELOW', (0, 1), (22, 1), 0.75, colors.HexColor('#003366')),
        ('TOPPADDING', (0, 0), (22, -1), 2),
        ('BOTTOMPADDING', (0, 0), (22, -1), 2),
        ('LEFTPADDING', (0, 0), (22, -1), 2),
        ('RIGHTPADDING', (0, 0), (22, -1), 2),
    ])

    for spec in colspan_specs:
        ts.add(*spec)

    table.setStyle(ts)
    elements.append(table)

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

@app.route('/exportar_reporte_pdf', methods=['GET', 'POST'])
def exportar_reporte_pdf():
    """
    Genera un PDF con la información de vacaciones según la plantilla institucional.
    Acepta los mismos filtros/parametros que la vista principal.
    """
    import io
    from datetime import datetime as _dt

    try:
        # Obtener filtro de UNES (opcional)
        unes_filter = request.args.get('unes', default=None, type=str)

        # Obtener y fusionar datos igual que /pbi-colaborador-vacaciones
        conn1 = get_db_connection()
        if not conn1:
            return jsonify({'ok': False, 'error': 'No se pudo conectar a BD_Integraciones'}), 500

        try:
            cursor1 = conn1.cursor()
            if unes_filter:
                unes_value = unes_filter[-3:] if len(unes_filter) >= 3 else unes_filter
                query1 = """
                    SELECT TOP 1200 * FROM BD_Integraciones.dbo.PBI_Colaborador_Vacaciones
                    WHERE RIGHT('000' + CAST(ISNULL(CAST(IDCia_CO AS VARCHAR), '') AS VARCHAR(20)), 3) = ?
                    ORDER BY Empleado
                """
                cursor1.execute(query1, (unes_value,))
            else:
                query1 = "SELECT TOP 1200 * FROM BD_Integraciones.dbo.PBI_Colaborador_Vacaciones ORDER BY Empleado"
                cursor1.execute(query1)
            rows1 = cursor1.fetchall()
            columns1 = [col[0] for col in (cursor1.description or [])]

            def serialize(value):
                if value is None:
                    return None
                try:
                    import decimal
                    if isinstance(value, decimal.Decimal):
                        return float(value)
                except Exception:
                    pass
                try:
                    return value.isoformat()
                except Exception:
                    return str(value)

            employees = []
            for row in rows1:
                item = {}
                for i, col in enumerate(columns1):
                    item[col] = serialize(row[i])
                employees.append(item)

            cursor1.close()
            conn1.close()
        except Exception as e:
            try:
                conn1.close()
            except Exception:
                pass
            return jsonify({'ok': False, 'error': f'Error al leer PBI_Colaborador_Vacaciones: {str(e)}'}), 500

        # Fusionar con asignaciones de BD2
        asignaciones = {}
        conn2 = get_db_connection2()
        if conn2:
            try:
                cursor2 = conn2.cursor()
                if unes_filter:
                    # Remove leading '2-' if present, then add it back
                    if unes_filter.lower().startswith('2-'):
                        unes_full = unes_filter  # Already has 2- prefix
                    else:
                        unes_full = f"2-{unes_filter}"
                    cursor2.execute("SELECT * FROM inf_asignacion WHERE unes = ?", (unes_full,))
                else:
                    cursor2.execute("SELECT * FROM inf_asignacion")
                rows2 = cursor2.fetchall()
                columns2 = [col[0] for col in (cursor2.description or [])]

                for row in rows2:
                    asig_item = {}
                    for i, col in enumerate(columns2):
                        asig_item[col] = row[i]
                    ident = asig_item.get('identificacion')
                    if ident:
                        asignaciones[str(ident)] = asig_item
                cursor2.close()
                conn2.close()
            except Exception as e:
                print(f"Error al obtener asignaciones de BD2: {e}")

        def format_date(val):
            if not val:
                return ''
            try:
                return val.strftime('%Y-%m-%d')
            except AttributeError:
                return str(val)[:10]

        for emp in employees:
            cedula_str = str(emp.get('cedula', ''))
            if cedula_str in asignaciones:
                match = asignaciones[cedula_str]
                emp['estado'] = match.get('estado_asignacion') or 'pendiente'
                emp['totalDiasTomados'] = match.get('total_dias_empleado') or 0
                emp['observaciones'] = match.get('observaciones') or ''
                emp['fechaIngreso'] = format_date(match.get('fecha_regreso'))
                emp['diaFamilia1'] = format_date(match.get('dia_familia1'))
                emp['diaFamilia2'] = format_date(match.get('dia_familia2'))
                emp['motivoRechazo'] = match.get('motivo_rechazo') or ''
                emp['th_asignacion'] = match.get('th_asignacion') or ''

                emp['periodos'] = [
                    {
                        'inicio': format_date(match.get('periodo1_fecha1')),
                        'fin': format_date(match.get('periodo1_fecha2')),
                        'dias': match.get('periodo1_dias1') or 0
                    },
                    {
                        'inicio': format_date(match.get('periodo2_fecha1')),
                        'fin': format_date(match.get('periodo2_fecha2')),
                        'dias': match.get('periodo2_dias2') or 0
                    },
                    {
                        'inicio': format_date(match.get('periodo3_fecha1')),
                        'fin': format_date(match.get('periodo3_fecha2')),
                        'dias': match.get('periodo3_dias3') or 0
                    }
                ]
            else:
                emp['estado'] = 'pendiente'
                emp['totalDiasTomados'] = 0
                emp['observaciones'] = ''
                emp['fechaIngreso'] = ''
                emp['diaFamilia1'] = ''
                emp['diaFamilia2'] = ''
                emp['motivoRechazo'] = ''
                emp['periodos'] = [
                    {'inicio': '', 'fin': '', 'dias': 0},
                    {'inicio': '', 'fin': '', 'dias': 0},
                    {'inicio': '', 'fin': '', 'dias': 0}
                ]

        # Determinar descripción de la UNES
        desc_unes = ''
        if employees:
            desc_unes = employees[0].get('DescCO', '') or ''

        pdf_bytes = generar_pdf_reporte_vacaciones(employees, unes_filter or '', desc_unes)

        # Nombre de archivo dinámico: 2-{unes}_vacaciones.pdf (ej. 2-123_vacaciones.pdf)
        unes_part = unes_filter if unes_filter else 'todos'
        if not unes_part.lower().startswith('2-'):
            unes_part = f"2-{unes_part}"
        filename = f"{unes_part}_vacaciones.pdf"

        from flask import send_file
        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        print(f"Error en exportar_reporte_pdf: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


def generar_plano_excel(rows_data, template_path, output_path):
    """
    Abre la plantilla Excel existente y escribe las filas generadas a partir de la fila 2 en adelante.
    Preserva la fila de encabezados (fila 1) y el resto de columnas no especificadas.

    Mapeo de columnas:
      - Columna B: consecutivo numérico autoincremental.
      - Columna C: identificación del empleado.
      - Columna G: fecha de inicio (formato texto YYYYMMDD).
      - Columna H: fecha de fin (formato texto YYYYMMDD).
      - Columna I: días del periodo.
    """
    from openpyxl import load_workbook
    from datetime import datetime

    wb = load_workbook(template_path)
    ws = wb.active

    for idx, row in enumerate(rows_data):
        excel_row = 2 + idx  # Comienza en fila 2 (fila 1 = encabezados)

        ws.cell(row=excel_row, column=1, value=2)
        
        # Columna B: consecutivo
        ws.cell(row=excel_row, column=2, value=idx + 1)

        # Columna C: identificación
        ws.cell(row=excel_row, column=3, value=row['identificacion'])
        
        ws.cell(row=excel_row, column=6, value=153)

        # Columna G: fecha inicio (YYYYMMDD)
        fecha_inicio = row.get('fecha_inicio')
        if fecha_inicio:
            ws.cell(row=excel_row, column=7, value=fecha_inicio)

        # Columna H: fecha fin (YYYYMMDD)
        fecha_fin = row.get('fecha_fin')
        if fecha_fin:
            ws.cell(row=excel_row, column=9, value=fecha_fin)

        # Columna I: dias
        ws.cell(row=excel_row, column=8, value=row['dias'])
        
        ws.cell(row=excel_row, column=10, value=0)        
        ws.cell(row=excel_row, column=12, value=0)        
        ws.cell(row=excel_row, column=19, value=0)
        ws.cell(row=excel_row, column=20, value=0)
        ws.cell(row=excel_row, column=21, value=0)
        ws.cell(row=excel_row, column=23, value=0)
        ws.cell(row=excel_row, column=24, value=0)
        ws.cell(row=excel_row, column=25, value=1)

    wb.save(output_path)

@app.route('/generar_plano', methods=['GET', 'POST'])
def generar_plano():
    """
    Genera el archivo plano de vacaciones en formato Excel.
    Recibe la opción 'general' o 'unes' desde el frontend.
    Si es por UNES, filtra la base de datos extrayendo los últimos 3 dígitos
    del campo unes (ej: '2-106' -> '106').
    """
    import io
    from datetime import datetime
    from flask import send_file

    try:
        # Capturar parámetros: GET o POST
        if request.method == 'POST':
            data = request.get_json(silent=True) or {}
            download_type = data.get('type', 'general')
            unes_select = data.get('unes', None)
        else:
            download_type = request.args.get('type', default='general')
            unes_select = request.args.get('unes', default=None)

        conn = get_db_connection2()
        if not conn:
            return jsonify({'ok': False, 'error': 'No se pudo conectar a vacacionesgyj'}), 500

        try:
            cursor = conn.cursor()

            # Consulta base
            query = """
                SELECT
                    vg.identificacion,
                    vg.unes,
                    vg.periodo1_fecha1,
                    vg.periodo1_fecha2,
                    vg.periodo1_dias1,
                    vg.periodo2_fecha1,
                    vg.periodo2_fecha2,
                    vg.periodo2_dias2,
                    vg.periodo3_fecha1,
                    vg.periodo3_fecha2,
                    vg.periodo3_dias3
                FROM vacacionesgyj.dbo.inf_asignacion vg
            """

            # Filtro por UNES: extraer últimos 3 dígitos
            if download_type == 'unes' and unes_select:
                unes_digits = str(unes_select)[-3:]
                query += " WHERE RIGHT(CAST(ISNULL(unes, '') AS VARCHAR(50)), 3) = ?"
                cursor.execute(query, (unes_digits,))
            else:
                cursor.execute(query)

            rows = cursor.fetchall()
            columns = [col[0] for col in (cursor.description or [])]

            def format_date_to_yyyymmdd(val):
                """Formatea una fecha a string YYYYMMDD."""
                if val is None or val == '':
                    return None
                try:
                    if hasattr(val, 'strftime'):
                        return val.strftime('%Y%m%d')
                    s = str(val)
                    # Intentar parsear común formats
                    for fmt in ('%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%Y-%m-%dT%H:%M:%S'):
                        try:
                            return datetime.strptime(s.split('.')[0].strip(), fmt).strftime('%Y%m%d')
                        except ValueError:
                            continue
                    # Si ya está en formato YYYYMMDD, devolverlo
                    if len(s) == 8 and s.isdigit():
                        return s
                    return None
                except Exception:
                    return None

            def safe_int(val):
                """Convierte a int, manejando None y decimal.Decimal."""
                if val is None or val == '':
                    return 0
                try:
                    return int(val)
                except (ValueError, TypeError):
                    try:
                        return int(float(val))
                    except (ValueError, TypeError):
                        return 0

            # Construir rows_data según la regla de desglose por periodos
            rows_data = []

            for row in rows:
                emp = dict(zip(columns, row))
                identificacion = emp.get('identificacion')

                # Periodo 1
                p1_fecha1 = emp.get('periodo1_fecha1')
                p1_fecha2 = emp.get('periodo1_fecha2')
                p1_dias = emp.get('periodo1_dias1')

                if p1_fecha1 and p1_fecha2:
                    rows_data.append({
                        'identificacion': identificacion,
                        'fecha_inicio': format_date_to_yyyymmdd(p1_fecha1),
                        'fecha_fin': format_date_to_yyyymmdd(p1_fecha2),
                        'dias': safe_int(p1_dias)
                    })

                # Periodo 2
                p2_fecha1 = emp.get('periodo2_fecha1')
                p2_fecha2 = emp.get('periodo2_fecha2')
                p2_dias = emp.get('periodo2_dias2')

                if p2_fecha1 and p2_fecha2:
                    rows_data.append({
                        'identificacion': identificacion,
                        'fecha_inicio': format_date_to_yyyymmdd(p2_fecha1),
                        'fecha_fin': format_date_to_yyyymmdd(p2_fecha2),
                        'dias': safe_int(p2_dias)
                    })

                # Periodo 3
                p3_fecha1 = emp.get('periodo3_fecha1')
                p3_fecha2 = emp.get('periodo3_fecha2')
                p3_dias = emp.get('periodo3_dias3')

                if p3_fecha1 and p3_fecha2:
                    rows_data.append({
                        'identificacion': identificacion,
                        'fecha_inicio': format_date_to_yyyymmdd(p3_fecha1),
                        'fecha_fin': format_date_to_yyyymmdd(p3_fecha2),
                        'dias': safe_int(p3_dias)
                    })

            cursor.close()
            conn.close()

            # Ruta de la plantilla
            import os
            template_path = os.path.join(os.path.dirname(__file__), 'planos_unoee', 'ARCHIVO PLANO TNL-VACACIONES.xlsx')

            if not os.path.exists(template_path):
                return jsonify({'ok': False, 'error': 'Plantilla Excel no encontrada'}), 500

            # Generar archivo temporal
            output_path = os.path.join(os.path.dirname(__file__), 'planos_unoee', 'plano_generado.xlsx')
            generar_plano_excel(rows_data, template_path, output_path)

            # Nombre del archivo
            if download_type == 'unes' and unes_select:
                unes_part = str(unes_select)
                filename = f"plano_vacaciones_unes_{unes_part}.xlsx"
            else:
                filename = 'plano_vacaciones_general.xlsx'

            # Retornar archivo
            return send_file(
                output_path,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=filename
            )

        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            print(f"Error en generar_plano: {e}")
            return jsonify({'ok': False, 'error': str(e)}), 500
    except Exception as e:
        print(f"Error en generar_plano: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500


if __name__ == '__main__':
    port = int(os.getenv('PORT2', 5000))
    debug2 = os.getenv('DEBUG2', 'True') == 'True'
    socketio.run(app, host='127.0.0.1', port=port, debug=debug2)
