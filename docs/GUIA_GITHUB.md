# Cómo subir FisIA a GitHub

## Antes de empezar
1. Cuenta en https://github.com (gratis).
2. Instala Git: https://git-scm.com/downloads
3. `LICENSE` ya incluye a los cuatro autores.
4. **Privacidad:** `static/profe.jpg` y las capturas de `docs/img/` muestran el rostro de tu profesor. Si el repositorio va a ser público, pídele permiso, o crea el repositorio como **Private** (y agrega al profesor como colaborador), o cambia `profe.jpg` por otra imagen.
5. **Comprueba que no exista un archivo `.env` dentro de la carpeta que vas a subir con tu clave real** (el `.gitignore` ya lo excluye, pero revísalo).

## Opción A: con la página de GitHub (sin comandos)
1. En GitHub pulsa **+ → New repository**. Nombre: `fisia`. Elige **Public** (o Private si prefieres). No marques "Add a README" (ya tienes uno). **Create repository**.
2. En la página del repo pulsa **uploading an existing file**.
3. Arrastra **el contenido** de la carpeta `fisia` (archivos y carpetas, no el `.zip`). Los archivos que empiezan con punto (`.gitignore`, `.gitattributes`, `.env.example`) pueden estar ocultos en tu explorador: activa "mostrar archivos ocultos".
4. Escribe un mensaje (por ejemplo `Primera versión`) y pulsa **Commit changes**.

## Opción B: con Git en la terminal (recomendada)
Dentro de la carpeta del proyecto:

```bash
git init
git add .
git status                      # verifica que NO aparezca .env
git commit -m "Primera versión de FisIA"
git branch -M main
git remote add origin https://github.com/TU_USUARIO/fisia.git
git push -u origin main
```

La primera vez, Git pide iniciar sesión: usa tu usuario y un **Personal Access Token** como contraseña (GitHub → Settings → Developer settings → Personal access tokens), o instala GitHub Desktop / usa `gh auth login`.

Con la CLI de GitHub (`gh`) puedes crear y subir todo de una vez:

```bash
gh auth login
gh repo create fisia --public --source=. --remote=origin --push
```

## Después de subir
- Reemplaza `TU_USUARIO` en el README (comando `git clone`) por tu usuario real.
- En el repo: **About → ⚙** para agregar descripción y temas (`physics`, `flask`, `gemini`, `education`).
- Etiqueta la versión: **Releases → Create a new release → v1.0.0**.
- Cambios futuros:
  ```bash
  git add .
  git commit -m "Describe el cambio"
  git push
  ```

## Si subiste tu clave por accidente
Revócala de inmediato en https://aistudio.google.com/apikey y crea otra. Borrar el archivo después **no** basta: queda en el historial.

## Para el profesor
Comparte el enlace del repositorio. Quien lo clone necesita su propia clave gratuita de Gemini (ver README).
