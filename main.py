from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import psycopg2
from typing import Optional

def obtener_conexion():
    try:
        return psycopg2.connect(
            host="localhost",
            database="lynko",          
            user="postgres",           
            password="1234",           
            port="5432"
        )
    except Exception as e:
        print(f"❌ Error crítico de conexión: {e}")
        return None

app = FastAPI()


app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory=".")

CORREO_ADMIN = "admin@lynko.com"
CONTRASENA_ADMIN = "Admin1234*"

@app.get("/", response_class=HTMLResponse)
def pag_landing(request: Request):
    return templates.TemplateResponse(request=request, name="landing.html")

@app.get("/login", response_class=HTMLResponse)
def pag_login(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(request=request, name="login.html", context={"error": error})

@app.post("/login")
def procesar_login(correo: str = Form(...), contrasena: str = Form(...)):
    if correo == CORREO_ADMIN and contrasena == CONTRASENA_ADMIN:
        return RedirectResponse(url="/admin", status_code=303)
        
    conn = obtener_conexion()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT id_usuario FROM usuarios WHERE correo = %s AND contraseña = %s AND rol = 'estudiante';", (correo, contrasena))
                usuario = cursor.fetchone()
                if usuario:
                    return RedirectResponse(url=f"/estudiante/{usuario[0]}", status_code=303)
        except Exception as e:
            print(f"⚠️ Error: {e}")
        finally:
            conn.close()
    return RedirectResponse(url="/login?error=Credenciales no encontradas", status_code=303)


@app.get("/admin", response_class=HTMLResponse)
def panel_admin(request: Request, msg: Optional[str] = None):
    conn = obtener_conexion()
    preguntas, usuarios, metricas_materias, mejores_examenes = [], [], [], []
    
    if conn:
        try:
            with conn.cursor() as cursor:
               
                cursor.execute("""
                    SELECT m.nombre, COUNT(i.id_intento), COALESCE(ROUND(AVG(i.nota_final), 1), 0), COUNT(CASE WHEN i.aprobado THEN 1 END)
                    FROM materias m LEFT JOIN examenes e ON m.id_materia = e.id_materia
                    LEFT JOIN intentos_examen i ON e.id_examen = i.id_examen GROUP BY m.nombre;
                """)
                metricas_materias = cursor.fetchall() or []
                
                
                cursor.execute("""
                    SELECT u.nombre, e.titulo, m.nombre, i.nota_final FROM intentos_examen i
                    JOIN usuarios u ON i.id_usuario = u.id_usuario JOIN examenes e ON i.id_examen = e.id_examen
                    JOIN materias m ON e.id_materia = m.id_materia ORDER BY i.nota_final DESC;
                """)
                mejores_examenes = cursor.fetchall() or []

                
                cursor.execute("SELECT p.id_pregunta, p.pregunta, m.nombre, p.nivel_dificultad FROM preguntas p JOIN materias m ON p.id_materia = m.id_materia ORDER BY p.id_pregunta ASC;")
                preguntas = cursor.fetchall() or []

                
                cursor.execute("""
                    SELECT u.id_usuario, u.nombre, u.correo, u.puntaje_total, COUNT(lu.id_logro) FROM usuarios u
                    LEFT JOIN logros_usuario lu ON u.id_usuario = lu.id_usuario WHERE u.rol = 'estudiante' 
                    GROUP BY u.id_usuario, u.nombre, u.correo, u.puntaje_total;
                """)
                usuarios = cursor.fetchall() or []
        except Exception as e:
            print(f"⚠️ Error en consultas: {e}")
        finally:
            conn.close()

    if not metricas_materias:
        metricas_materias = [("Matemáticas", 0, 0, 0), ("Español", 0, 0, 0), ("Biología", 0, 0, 0)]

    return templates.TemplateResponse(request=request, name="Admin.html", context={
        "preguntas": preguntas, "usuarios": usuarios,
        "metricas_materias": metricas_materias, "mejores_examenes": mejores_examenes, "msg": msg
    })

@app.post("/admin/preguntas/crear")
def crud_crear_pregunta(pregunta: str = Form(...), id_materia: int = Form(...), nivel: int = Form(...), puntos: int = Form(...), opcion1: str = Form(...), opcion2: str = Form(...), opcion3: str = Form(...), correcta: int = Form(...)):
    conn = obtener_conexion()
    msg = ""
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO preguntas (id_materia, pregunta, nivel_dificultad, puntos_recompensa) VALUES (%s, %s, %s, %s) RETURNING id_pregunta;", (id_materia, pregunta, nivel, puntos))
                id_p = cursor.fetchone()[0]
                cursor.execute("INSERT INTO opciones (id_pregunta, opcion, es_correcta) VALUES (%s, %s, %s);", (id_p, opcion1, True if correcta==1 else False))
                cursor.execute("INSERT INTO opciones (id_pregunta, opcion, es_correcta) VALUES (%s, %s, %s);", (id_p, opcion2, True if correcta==2 else False))
                cursor.execute("INSERT INTO opciones (id_pregunta, opcion, es_correcta) VALUES (%s, %s, %s);", (id_p, opcion3, True if correcta==3 else False))
                conn.commit()
            msg = "Pregunta añadida correctamente al banco"
        except Exception as e:
            msg = "Error al guardar la pregunta"
        finally:
            conn.close()
    return RedirectResponse(url=f"/admin?msg={msg}", status_code=303)

@app.get("/admin/preguntas/borrar/{id_pregunta}")
def crud_borrar_pregunta(id_pregunta: int):
    conn = obtener_conexion()
    msg = ""
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM preguntas WHERE id_pregunta = %s;", (id_pregunta,))
                conn.commit()
            msg = "Pregunta eliminada del sistema"
        except Exception as e:
            msg = "No se pudo eliminar la pregunta"
        finally:
            conn.close()
    return RedirectResponse(url=f"/admin?msg={msg}", status_code=303)

@app.get("/admin/estudiantes/eliminar/{id_usuario}")
def crud_eliminar_estudiante(id_usuario: int):
    conn = obtener_conexion()
    msg = ""
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM usuarios WHERE id_usuario = %s AND rol = 'estudiante';", (id_usuario,))
                conn.commit()
            msg = "Estudiante dado de baja correctamente"
        except Exception as e:
            msg = "No se pudo eliminar al estudiante"
        finally:
            conn.close()
    return RedirectResponse(url=f"/admin?msg={msg}", status_code=303)