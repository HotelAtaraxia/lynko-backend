from fastapi import APIRouter, Request, Form, HTTPException, Query, status, responses
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from database import obtener_conexion
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
import re
import os

# 📁 Configuración correcta del directorio base subiendo un nivel desde /routers
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=BASE_DIR)

# Inicializamos el router independiente
router = APIRouter()

# 📐 Esquemas de Validación Pydantic
class EstudianteActualizar(BaseModel):
    nombre: str = Field(..., min_length=2, description="El nombre debe tener al menos 2 letras")
    correo: str = Field(..., description="Correo electrónico del estudiante")
    contrasena: str = Field(..., min_length=8, description="La contraseña debe tener mínimo 8 caracteres")

    @field_validator('contrasena')
    @classmethod
    def validar_complejidad_contrasena(cls, v: str) -> str:
        if not re.search(r"[a-zA-Z]", v) or not re.search(r"[0-9]", v):
            raise ValueError("La contraseña debe combinar letras y números.")
        if len(set(v)) < 4:
            raise ValueError("La contraseña debe tener más variedad de caracteres diferentes.")
        return v

    @field_validator('correo')
    @classmethod
    def validar_formato_correo(cls, v: str) -> str:
        if "@" not in v or "." not in v:
            raise ValueError("El correo electrónico no es válido. ¡Revisa el formato!")
        return v

# 🧰 Funciones Internas de Soporte
def obtener_datos_base_estudiante(cursor, id_usuario: int):
    cursor.execute("""
        SELECT nombre, COALESCE(puntaje_total, 0), correo, contraseña, COALESCE(nivel, 0), COALESCE(dias_racha, 0)
        FROM usuarios WHERE id_usuario = %s;
    """, (id_usuario,))
    res = cursor.fetchone()
    
    if res:
        nombre_u, puntos_u, correo_u, contra_u, nivel_bd, racha_bd = res[0], res[1], res[2], res[3], res[4], res[5]
        
        if puntos_u >= 1000:
            nivel_calculado = 4
        elif puntos_u >= 500:
            nivel_calculado = 3
        elif puntos_u >= 200:
            nivel_calculado = 2
        elif puntos_u >= 100:
            nivel_calculado = 1
        else:
            nivel_calculado = 0  

        if nivel_calculado != nivel_bd:
            cursor.execute("UPDATE usuarios SET nivel = %s WHERE id_usuario = %s;", (nivel_calculado, id_usuario))

        return {
            "nombre": nombre_u, 
            "puntos": puntos_u, 
            "nivel": nivel_calculado,  
            "racha": racha_bd,          
            "correo": correo_u,
            "contrasena": contra_u,     
            "contraseña": contra_u      
        }
    return {"nombre": "Estudiante", "puntos": 0, "nivel": 0, "racha": 0, "correo": "", "contrasena": "", "contraseña": ""}

# 🌐 API pública de la Landing Page vinculada al router
@router.get("/api/preguntas-landing")
def obtener_preguntas_landing():
    conn = obtener_conexion()
    preguntas_data = []
    
    if conn:
        try:
            with conn.cursor() as cursor:
                # 🔍 Buscamos una pregunta aleatoria de Matemáticas, Español y Biología
                query = """
                    SELECT DISTINCT ON (p.id_materia) 
                        p.id_pregunta, m.nombre AS materia, p.pregunta, p.puntos_recompensa
                    FROM preguntas p
                    JOIN materias m ON p.id_materia = m.id_materia
                    ORDER BY p.id_materia, RANDOM();
                """
                cursor.execute(query)
                filas = cursor.fetchall()
                
                for fila in filas:
                    id_preg = fila[0]
                    
                    # Buscamos sus opciones correspondientes
                    cursor.execute("""
                        SELECT opcion, es_correcta 
                        FROM opciones 
                        WHERE id_pregunta = %s 
                        ORDER BY RANDOM();
                    """, (id_preg,))
                    filas_opciones = cursor.fetchall()
                    
                    opciones = [{"opcion": o[0], "es_correcta": bool(o[1])} for o in filas_opciones]
                    
                    preguntas_data.append({
                        "id_pregunta": id_preg,
                        "materia": fila[1].upper(),
                        "pregunta": fila[2],
                        "puntos": fila[3],
                        "opciones": opciones
                    })
        except Exception as e:
            print(f"⚠️ Error en la API de la landing: {e}")
        finally:
            conn.close()
            
    if not preguntas_data:
        # Si por alguna razón la BD está vacía, mandamos este preview de respaldo
        return [
            {
                "id_pregunta": 0,
                "materia": "MATEMÁTICAS",
                "pregunta": "Si el lince Lynko recolecta 5 manzanas por la mañana y 7 por la tarde, ¿cuántas manzanas tiene en total? 🍎",
                "puntos": 15,
                "opciones": [
                    {"opcion": "A) 10 manzanas", "es_correcta": False},
                    {"opcion": "B) 12 manzanas", "es_correcta": True},
                    {"opcion": "C) 15 manzanas", "es_correcta": False},
                    {"opcion": "D) 9 manzanas", "es_correcta": False}
                ]
            }
        ]
        
    return preguntas_data

# 🚀 Rutas de Navegación del Estudiante
@router.get("/inicio-estudiante/{id_usuario}", response_class=HTMLResponse)
def dashboard_estudiante_logeado(id_usuario: int, request: Request, vista_rapida: Optional[bool] = Query(None)):
    conn = obtener_conexion()
    datos = {"nombre": "Estudiante", "puntaje_total": 0, "nivel": 0, "dias_racha": 0}
    progreso_estudiante = {"Matemáticas": 0, "Español": 0, "Biología": 0}
    imagenes_materias = {"Matemáticas": None, "Español": None, "Biología": None}
    
    if conn:
        try:
            with conn.cursor() as cursor:
                query_usuario = "SELECT nombre, puntaje_total, nivel, dias_racha FROM usuarios WHERE id_usuario = %s AND activo = true"
                cursor.execute(query_usuario, (id_usuario,))
                usuario_db = cursor.fetchone()
                
                if usuario_db:
                    datos = {"nombre": usuario_db[0], "puntaje_total": usuario_db[1], "nivel": usuario_db[2], "dias_racha": usuario_db[3]}

                cursor.execute("SELECT nombre, link_imagen FROM materias;")
                for row in cursor.fetchall():
                    nombre_mat, link_img = row[0], row[1]
                    if nombre_mat in imagenes_materias:
                        imagenes_materias[nombre_mat] = link_img

                query_progreso = """
                    SELECT m.nombre AS materia, COUNT(p.id_pregunta) AS total_preguntas,
                           COUNT(ru.id_intento_respuesta) FILTER (WHERE ru.es_correcta = true) AS correctas
                    FROM materias m
                    LEFT JOIN preguntas p ON m.id_materia = p.id_materia
                    LEFT JOIN respuestas_usuario ru ON p.id_pregunta = ru.id_pregunta AND ru.id_usuario = %s
                    GROUP BY m.id_materia, m.nombre
                """
                cursor.execute(query_progreso, (id_usuario,))
                for fila in cursor.fetchall():
                    materia, total, correctas = fila[0], fila[1], fila[2]
                    progreso_estudiante[materia] = min(int((correctas / total) * 100), 100) if total > 0 else 0
        except Exception as e:
            print(f"⚠️ Error en Dashboard: {e}")
        finally:
            conn.close()
            
    return templates.TemplateResponse(
        request=request, name="inicio_lynko.html", 
        context={"request": request, "id_usuario": id_usuario, "vista_rapida": vista_rapida, "progreso": progreso_estudiante, "imagenes": imagenes_materias, **datos}
    )

@router.get("/materias-estudiante/{id_usuario}", response_class=HTMLResponse)
def vista_materias(request: Request, id_usuario: int):
    conn = obtener_conexion()
    materias_lista = []
    nombre_usuario, nivel_usuario, puntos_usuario, racha_usuario = "Estudiante", 1, 0, 0

    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT nombre, nivel, puntaje_total, dias_racha FROM usuarios WHERE id_usuario = %s AND rol = 'estudiante';", (id_usuario,))
                usuario_data = cursor.fetchone()
                if usuario_data:
                    nombre_usuario, nivel_usuario, puntos_usuario, racha_usuario = usuario_data[0], usuario_data[1], usuario_data[2], usuario_data[3]

                cursor.execute("""
                    SELECT m.id_materia, m.nombre, m.descripcion, m.link_imagen,
                           COALESCE((SELECT COUNT(*) FROM preguntas WHERE id_materia = m.id_materia), 0),
                           COALESCE((SELECT COUNT(DISTINCT ru.id_pregunta) FROM respuestas_usuario ru JOIN preguntas p ON ru.id_pregunta = p.id_pregunta WHERE p.id_materia = m.id_materia AND ru.id_usuario = %s AND ru.es_correcta = TRUE), 0)
                    FROM materias m;
                """, (id_usuario,))
                
                for row in cursor.fetchall():
                    total, hechas = row[4], row[5]
                    porcentaje = int((hechas / total) * 100) if total > 0 else 0
                    materias_lista.append({"id": row[0], "nombre": row[1], "descripcion": row[2], "link_imagen": row[3], "total_lecciones": total if total > 0 else 5, "lecciones_hechas": hechas, "progreso": min(porcentaje, 100)})
        except Exception as e:
            print(f"⚠️ Error en materias: {e}")
        finally:
            conn.close()

    return templates.TemplateResponse(request=request, name="Materias.html", context={"id_usuario": id_usuario, "nombre": nombre_usuario, "nivel": nivel_usuario, "puntos": puntos_usuario, "racha": racha_usuario, "materias": materias_lista})

@router.get("/actividades-estudiante/{id_usuario}", response_class=HTMLResponse)
def vista_actividades(id_usuario: int, request: Request, materia_filter: Optional[str] = Query("Todas")):
    conn = obtener_conexion()
    datos_user, actividades_lista = {}, []
    if conn:
        try:
            with conn.cursor() as cursor:
                datos_user = obtener_datos_base_estudiante(cursor, id_usuario)
                query = "SELECT p.id_pregunta, p.pregunta, m.descripcion, p.puntos_recompensa, m.nombre, EXISTS(SELECT 1 FROM respuestas_usuario WHERE id_pregunta = p.id_pregunta AND id_usuario = %s AND es_correcta = TRUE) FROM preguntas p JOIN materias m ON p.id_materia = m.id_materia"
                if materia_filter and materia_filter != "Todas":
                    query += " WHERE m.nombre = %s;"
                    cursor.execute(query, (id_usuario, materia_filter))
                else:
                    query += ";"
                    cursor.execute(query, (id_usuario,))
                
                for row in cursor.fetchall():
                    actividades_lista.append({"id": row[0], "titulo": f"Reto de {row[4]}", "descripcion": row[1], "puntos": row[3], "materia": row[4], "estado": "¡Hecho!" if row[5] else "Disponible"})
        finally:
            conn.close()
    return templates.TemplateResponse(request=request, name="Actividades.html", context={"id_usuario": id_usuario, **datos_user, "actividades": actividades_lista, "filtro_actual": materia_filter})

@router.get("/progreso-estudiante/{id_usuario}", response_class=HTMLResponse)
def reto_semanal_estudiante(id_usuario: int, request: Request):
    conn = obtener_conexion()
    reto_datos = {"titulo": "El Reino de las Plantas 🌿", "descripcion": "¡Las plantas dominan el mundo! Demuestra tus conocimientos...", "recompensa": 50, "emoji": "🏆", "dias_restantes": 3, "porcentaje_tiempo": 70}
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT titulo, descripcion, recompensa_exp, emoji, fecha_fin FROM retos_semanales WHERE activo = true LIMIT 1;")
                reto_db = cursor.fetchone()
                if reto_db:
                    dias_quedan = max(0, (reto_db[4] - datetime.now().date()).days)
                    reto_datos = {"titulo": reto_db[0], "descripcion": reto_db[1], "recompensa": reto_db[2], "emoji": reto_db[3], "dias_restantes": dias_quedan, "porcentaje_tiempo": int((dias_quedan / 7) * 100) if dias_quedan <= 7 else 100}
        except Exception as e:
            print(f"⚠️ Error Reto Semanal: {e}")
        finally:
            conn.close()
    return templates.TemplateResponse(request=request, name="Reto_semanal.html", context={"id_usuario": id_usuario, "reto": reto_datos})

@router.get("/recompensas-estudiante/{id_usuario}", response_class=HTMLResponse)
def vista_recompensas(id_usuario: int, request: Request):
    conn = obtener_conexion()
    datos_user, logros_lista = {}, []
    if conn:
        try:
            with conn.cursor() as cursor:
                datos_user = obtener_datos_base_estudiante(cursor, id_usuario)
                cursor.execute("SELECT l.id_logro, l.nombre, l.descripcion, l.imagen_medalla, EXISTS(SELECT 1 FROM logros_usuario WHERE id_logro = l.id_logro AND id_usuario = %s) FROM logros l;", (id_usuario,))
                for row in cursor.fetchall():
                    logros_lista.append({"id": row[0], "nombre": row[1], "descripcion": row[2], "icono": row[3], "ganado": row[4]})
        finally:
            conn.close()
    return templates.TemplateResponse(request=request, name="Recompensas.html", context={"id_usuario": id_usuario, **datos_user, "logros": logros_lista})

@router.get("/perfil-estudiante/{id_usuario}", response_class=HTMLResponse)
def vista_perfil(id_usuario: int, request: Request):
    conn = obtener_conexion()
    datos_user = {}
    if conn:
        try:
            with conn.cursor() as cursor:
                datos_user = obtener_datos_base_estudiante(cursor, id_usuario)
        finally:
            conn.close()
    return templates.TemplateResponse(request=request, name="Perfil.html", context={"id_usuario": id_usuario, **datos_user})

@router.get("/ajustes-estudiante/{id_usuario}", response_class=HTMLResponse)
def vista_ajustes(id_usuario: int, request: Request):
    conn = obtener_conexion()
    datos_user = {}
    if conn:
        try:
            with conn.cursor() as cursor:
                datos_user = obtener_datos_base_estudiante(cursor, id_usuario)
        finally:
            conn.close()
    return templates.TemplateResponse(request=request, name="Ajustes.html", context={"id_usuario": id_usuario, **datos_user})

@router.post("/ajustes-estudiante/{id_usuario}/guardar")
def actualizar_perfil_estudiante(id_usuario: int, nombre: str = Form(...), correo: str = Form(...), contrasena: str = Form(...)):
    conn = obtener_conexion()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute('UPDATE usuarios SET nombre = %s, correo = %s, "contraseña" = %s WHERE id_usuario = %s AND rol = \'estudiante\'', (nombre, correo, contrasena, id_usuario))
                conn.commit() 
        except Exception as e:
            print(f"Error: {e}")
        finally:
            conn.close()
    return responses.RedirectResponse(url=f"/perfil-estudiante/{id_usuario}", status_code=303)

# 🌐 Rutas API Puras (JSON)
@router.put("/api/estudiantes/{id_usuario}", status_code=status.HTTP_200_OK)
def actualizar_perfil_estudiante_api(id_usuario: int, datos: EstudianteActualizar):
    conn = obtener_conexion()
    if not conn: raise HTTPException(status_code=500, detail="No hay conexión")
    try:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE usuarios SET nombre = %s, correo = %s, contraseña = %s WHERE id_usuario = %s AND rol = 'estudiante';", (datos.nombre, datos.correo, datos.contrasena, id_usuario))
            if cursor.rowcount == 0: raise HTTPException(status_code=404, detail="Estudiante no encontrado.")
            conn.commit()
            return {"status": "success", "message": "¡Tus datos de perfil han sido modificados con éxito!"}
    except HTTPException as http_exc:
        if conn: conn.rollback()
        raise http_exc
    except Exception as e:
        if conn: conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally: conn.close()

@router.delete("/api/usuarios/{id_usuario}", status_code=status.HTTP_200_OK)
def dar_de_baja_usuario(id_usuario: int):
    conn = obtener_conexion()
    if not conn: raise HTTPException(status_code=500, detail="No hay conexión")
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM usuarios WHERE id_usuario = %s;", (id_usuario,))
            conn.commit()
            return {"status": "success", "message": "Borrado permanentemente."}
    except Exception as e:
        if conn: conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally: conn.close()