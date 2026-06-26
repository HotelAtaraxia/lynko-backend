from fastapi import APIRouter, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from database import obtener_conexion
from typing import Optional
import os

# 📁 Configuración del directorio base subiendo un nivel desde /routers
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=BASE_DIR)

# Inicializamos el router con el prefijo /admin
router = APIRouter(prefix="/admin")

@router.get("")
def panel_inicio(request: Request):
    conn = obtener_conexion()
    total_estudiantes = 0
    total_preguntas = 0
    promedio_exp = 0
    ultimas_preguntas = []
    mejores_estudiantes = [] # ⬅️ Variable nueva
    
    if conn:
        try:
            with conn.cursor() as cursor:
                # 1. Contar estudiantes
                cursor.execute("SELECT COUNT(*) FROM usuarios WHERE rol = 'estudiante';")
                total_estudiantes = cursor.fetchone()[0]
                
                # 2. Contar preguntas
                cursor.execute("SELECT COUNT(*) FROM preguntas;")
                total_preguntas = cursor.fetchone()[0]
                
                # 3. Promedio de EXP
                cursor.execute("SELECT COALESCE(AVG(puntaje_total), 0) FROM usuarios WHERE rol = 'estudiante';")
                promedio_exp = round(cursor.fetchone()[0], 1)
                
                # 4. Últimas 5 preguntas agregadas
                cursor.execute("""
                    SELECT p.id_pregunta, m.nombre, p.pregunta 
                    FROM preguntas p 
                    JOIN materias m ON p.id_materia = m.id_materia 
                    ORDER BY p.id_pregunta DESC LIMIT 5;
                """)
                ultimas_preguntas = cursor.fetchall()
                
                # 5. Obtener los mejores 5 estudiantes para la nueva tabla 🏆
                cursor.execute("""
                    SELECT id_usuario, nombre, correo, puntaje_total, nivel 
                    FROM usuarios 
                    WHERE rol = 'estudiante' 
                    ORDER BY puntaje_total DESC LIMIT 5;
                """)
                mejores_estudiantes = cursor.fetchall()
                
        except Exception as e:
            print(f"⚠️ Error cargando métricas del dashboard: {e}")
        finally:
            conn.close()

    # Retornamos el contexto completo alineado con el nuevo HTML
    return templates.TemplateResponse(
        request=request,
        name="Admin.html",
        context={
            "total_estudiantes": total_estudiantes,
            "total_preguntas": total_preguntas,
            "promedio_exp": promedio_exp,
            "ultimas_preguntas": ultimas_preguntas,
            "mejores_estudiantes": mejores_estudiantes # ⬅️ Se envía al HTML
        }
    )


@router.post("/nuevas-preguntas")
def crear_pregunta(
    pregunta: str = Form(...), 
    id_materia: int = Form(...), 
    nivel: int = Form(...), 
    puntos: int = Form(...), 
    opcion1: str = Form(...), 
    opcion2: str = Form(...), 
    opcion3: str = Form(...), 
    correcta: str = Form(...)
):
    conn = obtener_conexion()
    msg = ""
    if conn:
        try:
            opcion_correcta_int = int(correcta)
            with conn.cursor() as cursor:
                # 1. Insertamos la pregunta principal
                cursor.execute("""
                    INSERT INTO preguntas (id_materia, pregunta, nivel_dificultad, puntos_recompensa) 
                    VALUES (%s, %s, %s, %s) 
                    RETURNING id_pregunta;
                """, (id_materia, pregunta, nivel, puntos))
                
                id_p = cursor.fetchone()[0]
                
                # 2. Insertamos las opciones
                cursor.execute("INSERT INTO opciones (id_pregunta, opcion, es_correcta) VALUES (%s, %s, %s);", 
                               (id_p, opcion1, True if opcion_correcta_int == 1 else False))
                               
                cursor.execute("INSERT INTO opciones (id_pregunta, opcion, es_correcta) VALUES (%s, %s, %s);", 
                               (id_p, opcion2, True if opcion_correcta_int == 2 else False))
                               
                cursor.execute("INSERT INTO opciones (id_pregunta, opcion, es_correcta) VALUES (%s, %s, %s);", 
                               (id_p, opcion3, True if opcion_correcta_int == 3 else False))
                
                conn.commit()
                msg = "Pregunta añadida correctamente al banco"
                print("✅ [ÉXITO] Pregunta y opciones guardadas correctamente.")
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"❌ [ERROR CRÍTICO EN BD]: {e}")
            msg = "Error interno al guardar la pregunta"
        finally:
            conn.close()
    else:
        msg = "Error de conexión con el servidor"
            
    return RedirectResponse(url=f"/admin?msg={msg}", status_code=303)


@router.get("/preguntas", response_class=HTMLResponse)
def vista_admin_preguntas(request: Request):
    conn = obtener_conexion()
    lista_preguntas = []
    
    if conn:
        try:
            with conn.cursor() as cursor:
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
                        "opciones": row[5]
                    })
        except Exception as e:
            print(f"⚠️ Error al listar preguntas: {e}")
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
            print(f"⚠️ Error al eliminar pregunta {id_pregunta}: {e}")
            msg = "No se pudo eliminar la pregunta"
        finally:
            conn.close()
    return RedirectResponse(url=f"/admin?msg={msg}", status_code=303)

@router.post("/preguntas/editar")
def procesar_edicion_pregunta(
    id_pregunta: int = Form(...), 
    id_materia: int = Form(...), # ⬅️ Nuevo campo capturado del formulario
    pregunta: str = Form(...), 
    puntos: int = Form(...)
):
    conn = obtener_conexion()
    if conn:
        try:
            with conn.cursor() as cursor:
                # ⚙️ SQL modificado para actualizar también la materia vinculada
                cursor.execute("""
                    UPDATE preguntas 
                    SET id_materia = %s, pregunta = %s, puntos_recompensa = %s 
                    WHERE id_pregunta = %s;
                """, (id_materia, pregunta, puntos, id_pregunta))
            conn.commit()
        except Exception as e:
            print(f"⚠️ Error al actualizar pregunta y materia: {e}")
        finally:
            conn.close()
            
    return RedirectResponse(url="/admin/preguntas?msg=Pregunta+actualizada+con+éxito+✨", status_code=303)

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
            msg = "Datos actualizados correctamente"
        except Exception as e:
            print(f"⚠️ Error al actualizar estudiante {id_usuario}: {e}")
            msg = "Error al guardar los cambios"
        finally:
            conn.close()
            
    # 💡 CORRECCIÓN AQUÍ: Cambia la redirección para que use la barra diagonal del prefijo correctamente
    return RedirectResponse(url="/admin/estudiantes", status_code=303)


@router.get("/estudiantes")
def lista_estudiantes(request: Request, q: str = None):
    conn = obtener_conexion()
    lista_usuarios = []
    
    if conn:
        with conn.cursor() as cursor:
            if q and q.strip():
                # 🔍 Limpiamos el texto de búsqueda
                termino = f"%{q.strip()}%"
                
                # Intentamos ver si el término es un número entero para buscar por ID o Puntos exactos
                es_numero = q.strip().isdigit()
                
                if es_numero:
                    # Si es número, busca coincidencia en Nombre, ID exacto o EXP exacta
                    query = """
                        SELECT id_usuario, nombre, correo, puntaje_total, nivel 
                        FROM usuarios 
                        WHERE rol = 'estudiante' 
                          AND (nombre LIKE %s OR id_usuario = %s OR puntaje_total = %s)
                        ORDER BY puntaje_total DESC;
                    """
                    cursor.execute(query, (termino, int(q.strip()), int(q.strip())))
                else:
                    # Si es texto, solo busca por coincidencia en el nombre
                    query = """
                        SELECT id_usuario, nombre, correo, puntaje_total, nivel 
                        FROM usuarios 
                        WHERE rol = 'estudiante' 
                          AND nombre LIKE %s
                        ORDER BY puntaje_total DESC;
                    """
                    cursor.execute(query, (termino,))
            else:
                # Si no hay búsqueda, trae a todos
                cursor.execute("""
                    SELECT id_usuario, nombre, correo, puntaje_total, nivel 
                    FROM usuarios 
                    WHERE rol = 'estudiante' 
                    ORDER BY puntaje_total DESC;
                """)
            
            # Recuperamos las tuplas (recuerda que tu HTML actual lee índices: estudiante[0], estudiante[1]...)
            lista_usuarios = cursor.fetchall()
            
        conn.close()
    
    return templates.TemplateResponse(
        request=request,
        name="Ver-estudiantes.html", # Asegúrate de que coincida con el nombre exacto de tu archivo de lista
        context={
            "usuarios": lista_usuarios,
            "query_busqueda": q
        }
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
            print(f"⚠️ Error al eliminar usuario {id_usuario}: {e}")
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
            
    return templates.TemplateResponse(request=request, name="Ver-estudiantes.html", context={"estudiantes": estudiantes_ranking})

@router.get("/estudiantes/ver/{id_usuario}", response_class=HTMLResponse)
def ver_expediente_estudiante(id_usuario: int, request: Request):
    conn = obtener_conexion()
    estudiante = None
    historial_respuestas = []
    logros_ganados = []

    if conn:
        try:
            with conn.cursor() as cursor:
                # 1. Información general del estudiante
                cursor.execute("""
                    SELECT id_usuario, nombre, correo, puntaje_total, nivel, dias_racha, fecha_registro 
                    FROM usuarios WHERE id_usuario = %s AND rol = 'estudiante';
                """, (id_usuario,))
                usuario_db = cursor.fetchone()
                
                if usuario_db:
                    estudiante = {
                        "id": usuario_db[0], "nombre": usuario_db[1], "correo": usuario_db[2],
                        "puntos": usuario_db[3], "nivel": usuario_db[4], "racha": usuario_db[5],
                        "registro": usuario_db[6]
                    }

                    # 2. Historial de preguntas respondidas (Une usuarios -> respuestas_usuario -> preguntas -> materias)
                    cursor.execute("""
                        SELECT m.nombre, p.pregunta, ru.es_correcta, ru.fecha_respuesta
                        FROM respuestas_usuario ru
                        JOIN preguntas p ON ru.id_pregunta = p.id_pregunta
                        JOIN materias m ON p.id_materia = m.id_materia
                        WHERE ru.id_usuario = %s
                        ORDER BY ru.fecha_respuesta DESC;
                    """, (id_usuario,))
                    for row in cursor.fetchall():
                        historial_respuestas.append({
                            "materia": row[0], "pregunta": row[1], "correcta": row[2], "fecha": row[3]
                        })

                    # 3. Logros o medallas obtenidas
                    cursor.execute("""
                        SELECT l.nombre, l.descripcion, l.imagen_medalla, lu.fecha_ganado
                        FROM logros_usuario lu
                        JOIN logros l ON lu.id_logro = l.id_logro
                        WHERE lu.id_usuario = %s
                        ORDER BY lu.fecha_ganado DESC;
                    """, (id_usuario,))
                    for row in cursor.fetchall():
                        logros_ganados.append({
                            "nombre": row[0], "descripcion": row[1], "icono": row[2], "fecha": row[3]
                        })
        except Exception as e:
            print(f"⚠️ Error al consultar expediente del estudiante {id_usuario}: {e}")
        finally:
            conn.close()

    if not estudiante:
        return RedirectResponse(url="/admin/estudiantes?msg=Estudiante no encontrado", status_code=303)

    # Renderizamos una nueva plantilla para el expediente
    return templates.TemplateResponse(
        request=request,
        name="admin-ver-mas.html", 
        context={"estudiante": estudiante, "respuestas": historial_respuestas, "logros": logros_ganados}
    )