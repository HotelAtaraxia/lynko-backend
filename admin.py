from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from database import obtener_conexion
from typing import Optional

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory=".")

@router.get("", response_class=HTMLResponse)
def panel_admin(request: Request, msg: Optional[str] = None):
    conn = obtener_conexion()
    preguntas, usuarios, metricas_materias, mejores_examenes = [], [], [], []
    
    if conn:
        try:
            with conn.cursor() as cursor:
                # 1. Métricas de efectividad por materia
                cursor.execute("""
                    SELECT m.nombre, COUNT(i.id_intento), COALESCE(ROUND(AVG(i.nota_final), 1), 0), COUNT(CASE WHEN i.aprobado THEN 1 END)
                    FROM materias m LEFT JOIN examenes e ON m.id_materia = e.id_materia
                    LEFT JOIN intentos_examen i ON e.id_examen = i.id_examen GROUP BY m.nombre;
                """)
                metricas_materias = cursor.fetchall() or []
                
                # 2. Historial de mejores exámenes rendidos
                cursor.execute("""
                    SELECT u.nombre, e.titulo, m.nombre, i.nota_final FROM intentos_examen i
                    JOIN usuarios u ON i.id_usuario = u.id_usuario JOIN examenes e ON i.id_examen = e.id_examen
                    JOIN materias m ON e.id_materia = m.id_materia ORDER BY i.nota_final DESC;
                """)
                mejores_examenes = cursor.fetchall() or []

                # 3. Listado completo de preguntas del sistema
                cursor.execute("SELECT p.id_pregunta, p.pregunta, m.nombre, p.nivel_dificultad FROM preguntas p JOIN materias m ON p.id_materia = m.id_materia ORDER BY p.id_pregunta ASC;")
                preguntas = cursor.fetchall() or []

                # 4. Listado de estudiantes y suma de sus logros obtenidos
                cursor.execute("""
                    SELECT u.id_usuario, u.nombre, u.correo, u.puntaje_total, COUNT(lu.id_logro) FROM usuarios u
                    LEFT JOIN logros_usuario lu ON u.id_usuario = lu.id_usuario WHERE u.rol = 'estudiante' 
                    GROUP BY u.id_usuario, u.nombre, u.correo, u.puntaje_total
                    ORDER BY u.id_usuario ASC;
                """)
                usuarios = cursor.fetchall() or []
        except Exception as e:
            print(f"⚠️ Error en consultas del Panel Admin: {e}")
        finally:
            conn.close()

    if not metricas_materias:
        metricas_materias = [("Matemáticas", 0, 0, 0), ("Español", 0, 0, 0), ("Biología", 0, 0, 0)]

    return templates.TemplateResponse(request=request, name="Admin.html", context={
        "preguntas": preguntas, "usuarios": usuarios,
        "metricas_materias": metricas_materias, "mejores_examenes": mejores_examenes, "msg": msg
    })


@router.post("/nuevas-preguntas")
def crear_pregunta(
    pregunta: str = Form(...), 
    id_materia: int = Form(...), 
    nivel: int = Form(...), 
    puntos: int = Form(...), 
    opcion1: str = Form(...), 
    opcion2: str = Form(...), 
    opcion3: str = Form(...), 
    correcta: str = Form(...)  # 👈 Lo recibimos como str para evitar conflictos de tipo de dato
):
    conn = obtener_conexion()
    msg = ""
    if conn:
        try:
            # Forzamos la conversión a entero de forma segura
            opcion_correcta_int = int(correcta)
            
            with conn.cursor() as cursor:
                # 1. Insertamos la pregunta principal
                cursor.execute("""
                    INSERT INTO preguntas (id_materia, pregunta, nivel_dificultad, puntos_recompensa) 
                    VALUES (%s, %s, %s, %s) 
                    RETURNING id_pregunta;
                """, (id_materia, pregunta, nivel, puntos))
                
                id_p = cursor.fetchone()[0]
                
                # 2. Insertamos las opciones comparando de forma estricta con el entero convertido
                cursor.execute("INSERT INTO opciones (id_pregunta, opcion, es_correcta) VALUES (%s, %s, %s);", 
                               (id_p, opcion1, True if opcion_correcta_int == 1 else False))
                               
                cursor.execute("INSERT INTO opciones (id_pregunta, opcion, es_correcta) VALUES (%s, %s, %s);", 
                               (id_p, opcion2, True if opcion_correcta_int == 2 else False))
                               
                cursor.execute("INSERT INTO opciones (id_pregunta, opcion, es_correcta) VALUES (%s, %s, %s);", 
                               (id_p, opcion3, True if opcion_correcta_int == 3 else False))
                
                # 3. Confirmamos los cambios de manera persistente en PostgreSQL
                conn.commit()
                msg = "Pregunta añadida correctamente al banco"
                print("✅ [ÉXITO] Pregunta y opciones guardadas correctamente en la base de datos.")
                
        except Exception as e:
            if conn:
                conn.rollback()  # 👈 Deshace los cambios si hubo error para no dejar datos corruptos
            print(f"❌ [ERROR CRÍTICO EN BD]: {e}")
            msg = "Error interno al guardar la pregunta"
        finally:
            conn.close()
    else:
        print("❌ [ERROR DE CONEXIÓN]: No se pudo conectar a PostgreSQL.")
        msg = "Error de conexión con el servidor"
            
    return RedirectResponse(url=f"/admin?msg={msg}", status_code=303)


@router.get("/preguntas", response_class=HTMLResponse)
def vista_admin_preguntas(request: Request):
    conn = obtener_conexion()
    lista_preguntas = []
    
    if conn:
        try:
            with conn.cursor() as cursor:
                # Usamos JSON_AGG para traer todas las opciones asociadas a cada pregunta de forma limpia
                cursor.execute("""
                    SELECT p.id_pregunta, m.nombre AS materia, p.pregunta, p.nivel_dificultad, p.puntos_recompensa,
                           json_agg(json_build_object('opcion', o.opcion, 'es_correcta', o.es_correcta)) AS opciones
                    FROM preguntas p
                    JOIN materias m ON p.id_materia = m.id_materia
                    LEFT JOIN opciones o ON p.id_pregunta = o.id_pregunta
                    GROUP BY p.id_pregunta, m.nombre
                    ORDER BY p.id_pregunta DESC;
                """)
                for row in cursor.fetchall():
                    lista_preguntas.append({
                        "id_pregunta": row[0],
                        "materia": row[1],
                        "pregunta": row[2],
                        "nivel": row[3],
                        "puntos": row[4],
                        "opciones": row[5]  # Contiene el arreglo de opciones con su texto y si es correcta o no
                    })
        except Exception as e:
            print(f"⚠️ Error al listar preguntas y respuestas para el administrador: {e}")
        finally:
            conn.close()

    return templates.TemplateResponse(
        request=request,
        name="admin-preguntas.html",
        context={"preguntas": lista_preguntas}
    )



@router.get("/preguntas/borrar/{id_pregunta}")
def borrar_pregunta(id_pregunta: int):
    conn = obtener_conexion()
    msg = ""
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM preguntas WHERE id_pregunta = %s;", (id_pregunta,))
                conn.commit()
            msg = "Pregunta eliminada del sistema"
        except Exception as e:
            print(f"⚠️ Error al eliminar la pregunta {id_pregunta}: {e}")
            msg = "No se pudo eliminar la pregunta"
        finally:
            conn.close()
    return RedirectResponse(url=f"/admin?msg={msg}", status_code=303)


@router.post("/estudiantes/editar")
def editar_estudiante(
    id_usuario: int = Form(...), 
    nombre: str = Form(...), 
    correo: str = Form(...), 
    puntaje_total: int = Form(...)
):
    conn = obtener_conexion()
    msg = ""
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    UPDATE usuarios 
                    SET nombre = %s, 
                        correo = %s, 
                        puntaje_total = %s 
                    WHERE id_usuario = %s AND rol = 'estudiante';
                """, (nombre, correo, puntaje_total, id_usuario))
                conn.commit()
            msg = "Datos del estudiante actualizados correctamente"
        except Exception as e:
            print(f"⚠️ Error al actualizar el estudiante {id_usuario}: {e}")
            msg = "No se pudieron guardar los cambios del alumno"
        finally:
            conn.close()
    return RedirectResponse(url=f"/admin?msg={msg}", status_code=303)


@router.get("/estudiantes", response_class=HTMLResponse)
def vista_ver_estudiantes(request: Request):
    conn = obtener_conexion()
    lista_estudiantes = []
    
    if conn:
        try:
            with conn.cursor() as cursor:
                # Traemos solo a los usuarios con rol de estudiante
                cursor.execute("""
                    SELECT id_usuario, nombre, correo, puntaje_total, nivel, dias_racha
                    FROM usuarios
                    WHERE rol = 'estudiante'
                    ORDER BY id_usuario ASC;
                """)
                for row in cursor.fetchall():
                    lista_estudiantes.append({
                        "id_usuario": row[0],
                        "nombre": row[1],
                        "correo": row[2],
                        "puntaje_total": row[3],
                        "nivel": row[4],
                        "dias_racha": row[5]
                    })
        except Exception as e:
            print(f"⚠️ Error al listar estudiantes para el administrador: {e}")
        finally:
            conn.close()

    return templates.TemplateResponse(
        request=request,
        name="Ver-estudiantes.html", # Coincide con tu archivo físico Ver-estudiantes.html
        context={"estudiantes": lista_estudiantes}
    )

@router.get("/estudiantes/eliminar/{id_usuario}")
def dar_baja_estudiante(id_usuario: int):
    conn = obtener_conexion()
    msg = ""
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM usuarios WHERE id_usuario = %s AND rol = 'estudiante';", (id_usuario,))
                conn.commit()
            msg = "Estudiante dado de baja correctamente"
        except Exception as e:
            print(f"⚠️ Error al eliminar al usuario {id_usuario}: {e}")
            msg = "No se pudo eliminar al estudiante"
        finally:
            conn.close()
    return RedirectResponse(url=f"/admin?msg={msg}", status_code=303)


@router.get("/nuevas-preguntas", response_class=HTMLResponse)
def vista_nuevas_preguntas(request: Request):
    return templates.TemplateResponse(request=request, name="Nuevas_preguntas.html")


@router.get("/ranking", response_class=HTMLResponse)
def ver_ranking(request: Request):
    conn = obtener_conexion()
    estudiantes_ranking = []
    if conn:
        try:
            with conn.cursor() as cursor:
                # CORREGIDO: Se quitó 'AND activo = TRUE' ya que la columna no existe en tu script.sql
                cursor.execute("""
                    SELECT nombre, nivel, puntaje_total 
                    FROM usuarios 
                    WHERE rol = 'estudiante' 
                    ORDER BY puntaje_total DESC LIMIT 10;
                """)
                estudiantes_ranking = cursor.fetchall()
        except Exception as e:
            print(f"⚠️ Error al obtener el ranking: {e}")
        finally:
            conn.close()
            
    return templates.TemplateResponse(request=request, name="Ranking.html", context={"estudiantes": estudiantes_ranking})