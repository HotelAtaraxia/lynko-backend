from fastapi import FastAPI, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from database import obtener_conexion
from typing import Optional
import re
import os

# Importamos los routers de los módulos separados
from routers import estudiantes  
from routers import admin

app = FastAPI(title="Lynko API - Ecosistema Backend")

# 📁 SOLUCIÓN AL ERROR DE CAMINO: Definimos la raíz absoluta del proyecto
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Configuración de Archivos Estáticos y Plantillas usando rutas absolutas
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=BASE_DIR)

# 🛠️ Inclusión de Routers (Unificación del Sistema)
app.include_router(admin.router)
app.include_router(estudiantes.router)

# 📡 Middleware de rastreo global
@app.middleware("http")
async def middleware_rastreo_lynko(request: Request, call_next):
    print(f"📡 [Middleware] Petición entrante: {request.method} a {request.url.path}")
    response = await call_next(request)
    return response

# 🛑 Manejo de Errores Globales
@app.exception_handler(404)
async def error_404_personalizado(request: Request, exc: HTTPException):
    return RedirectResponse(url="/login?error=La pagina solicitada no existe", status_code=303)

@app.exception_handler(500)
async def error_500_personalizado(request: Request, exc: Exception):
    print(f"🔥 Error Crítico 500 (Servidor): {exc}")
    return HTMLResponse(
        content="<h2>⚠️ Ocurrió un error inesperado en el servidor Lynko. Verifica PostgreSQL o la ubicación de tus HTML.</h2>", 
        status_code=500
    )

# 🏠 Rutas Públicas / Acceso
@app.get("/", response_class=HTMLResponse)
def index_landing(request: Request):
    return templates.TemplateResponse(request=request, name="landing.html")

@app.get("/login", response_class=HTMLResponse)
def vista_login(request: Request, error: Optional[str] = None, msg: Optional[str] = None):
    return templates.TemplateResponse(request=request, name="Login.html", context={"error": error, "msg": msg})

@app.get("/registro", response_class=HTMLResponse)
def vista_registro(request: Request, error: Optional[str] = None):
    return templates.TemplateResponse(request=request, name="Registro.html", context={"error": error})

@app.post("/login")
def procesar_login(correo: str = Form(...), contrasena: str = Form(...)):
    conn = obtener_conexion()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    SELECT id_usuario, correo, rol 
                    FROM usuarios 
                    WHERE correo = %s AND contraseña = %s AND activo = TRUE;
                """, (correo, contrasena))
                usuario = cursor.fetchone()
                
                if usuario:
                    id_u, correo_bd, rol = usuario[0], usuario[1], usuario[2]
                    if str(rol).strip().lower() == "admin":
                        return RedirectResponse(url="/admin", status_code=303)
                    else:
                        return RedirectResponse(url=f"/inicio-estudiante/{id_u}", status_code=303)
        except Exception as e:
            print(f"⚠️ Error en login: {e}")
        finally:
            conn.close()
    return RedirectResponse(url="/login?error=Credenciales incorrectas o usuario inactivo", status_code=303)

@app.post("/registro")
def procesar_registro(nombre: str = Form(...), correo: str = Form(...), contrasena: str = Form(...)):
    if len(contrasena) < 8 or not re.search(r"[a-zA-Z]", contrasena) or not re.search(r"[0-9]", contrasena) or len(set(contrasena)) < 4:
        return RedirectResponse(url="/registro?error=Contraseña insegura. Debe tener mínimo 8 caracteres con letras y números.", status_code=303)

    conn = obtener_conexion()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO usuarios (nombre, correo, contraseña, rol, puntaje_total, activo) 
                    VALUES (%s, %s, %s, 'estudiante', 0, TRUE) RETURNING id_usuario;
                """, (nombre, correo, contrasena))
                nuevo_id = cursor.fetchone()[0]
                
                try:
                    cursor.execute("INSERT INTO logros_usuario (id_usuario, id_logro) VALUES (%s, 1);", (nuevo_id,))
                except Exception:
                    pass
                
                conn.commit()
                return RedirectResponse(url=f"/inicio-estudiante/{nuevo_id}", status_code=303)
        except Exception as e:
            print(f"⚠️ Error al registrar: {e}")
            return RedirectResponse(url="/registro?error=El correo ya está registrado", status_code=303)
        finally:
            conn.close()
    return RedirectResponse(url="/registro?error=Error de conexión", status_code=303)