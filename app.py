from flask import Flask, request, jsonify, send_file, render_template
from compressor import compress_image
from io import BytesIO
from flask import render_template
import io
import zipfile
from flask import Response



app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff'}

@app.route('/test')
def test_page():
    return render_template('index.html')

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS




@app.route('/')
def home():
    return render_template('index.html')

@app.route('/compress', methods=['POST'])
def compress():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not supported'}), 400

    try:
        target_min = int(request.form.get('target_min', 17))
        target_max = int(request.form.get('target_max', 20))
    except ValueError:
        return jsonify({'error': 'Invalid target size'}), 400

    result_bytes, original_kb, final_kb, success = compress_image(
        file, target_min, target_max
    )

    output = BytesIO(result_bytes)
    output.seek(0)

    original_name = file.filename.rsplit('.', 1)[0]
    download_name = f"{original_name}_compressed.jpg"

    response = send_file(
        output,
        mimetype='image/jpeg',
        as_attachment=True,
        download_name=download_name
    )

    response.headers['X-Original-KB'] = str(original_kb)
    response.headers['X-Final-KB']    = str(final_kb)
    response.headers['X-Success']     = str(success)

    return response


@app.route('/compress-folder', methods=['POST'])
def compress_folder():
    files = request.files.getlist('folder_files')

    if not files or len(files) == 0:
        return jsonify({'error': 'No files uploaded'}), 400

    try:
        target_min = int(request.form.get('target_min', 17))
        target_max = int(request.form.get('target_max', 20))
    except ValueError:
        return jsonify({'error': 'Invalid target size'}), 400

    # Get the root folder name from the first file path
    # Browser sends full relative path like: my_photos/docs/id_card.jpg
    first_path = request.form.getlist('file_paths')[0] if request.form.getlist('file_paths') else ''
    root_folder = first_path.split('/')[0] if '/' in first_path else 'folder'
    zip_folder_name = root_folder + '_compressed'

    # Get all file paths sent from frontend
    file_paths = request.form.getlist('file_paths')

    zip_buffer = io.BytesIO()
    success_count = 0
    fail_count = 0

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for file, file_path in zip(files, file_paths):
            if file.filename == '':
                continue
            if not allowed_file(file.filename):
                continue

            try:
                result_bytes, original_kb, final_kb, success = compress_image(
                    file, target_min, target_max
                )

                # Rebuild path inside ZIP
                # Original: my_photos/docs/id_card.jpg
                # Inside ZIP: my_photos_compressed/docs/id_card.jpg
                path_parts = file_path.split('/')
                path_parts[0] = zip_folder_name

                # Keep original filename, change extension to .jpg
                original_name = path_parts[-1].rsplit('.', 1)[0] + '.jpg'
                path_parts[-1] = original_name

                zip_path = '/'.join(path_parts)
                zip_file.writestr(zip_path, result_bytes)

                if success:
                    success_count += 1
                else:
                    fail_count += 1

            except Exception as e:
                fail_count += 1
                continue

    zip_buffer.seek(0)

    response = send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'{zip_folder_name}.zip'
    )

    response.headers['X-Success-Count'] = str(success_count)
    response.headers['X-Fail-Count'] = str(fail_count)
    response.headers['X-Total'] = str(success_count + fail_count)
    response.headers['X-Folder-Name'] = zip_folder_name

    return response

@app.route('/compress-bulk', methods=['POST'])
def compress_bulk():
    files = request.files.getlist('files')

    if not files or len(files) == 0:
        return jsonify({'error': 'No files uploaded'}), 400

    try:
        target_min = int(request.form.get('target_min', 17))
        target_max = int(request.form.get('target_max', 20))
    except ValueError:
        return jsonify({'error': 'Invalid target size'}), 400

    # Create ZIP in memory
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        success_count = 0
        fail_count = 0

        for file in files:
            if file.filename == '':
                continue

            if not allowed_file(file.filename):
                continue

            try:
                result_bytes, original_kb, final_kb, success = compress_image(
                    file, target_min, target_max
                )

                original_name = file.filename.rsplit('.', 1)[0]
                output_name = f"{original_name}_compressed.jpg"

                zip_file.writestr(output_name, result_bytes)

                if success:
                    success_count += 1
                else:
                    fail_count += 1

            except Exception as e:
                fail_count += 1
                continue

    zip_buffer.seek(0)

    response = send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='compresskit_bulk.zip'
    )

    response.headers['X-Success-Count'] = str(success_count)
    response.headers['X-Fail-Count'] = str(fail_count)
    response.headers['X-Total'] = str(success_count + fail_count)

    return response

@app.route('/sitemap.xml')
def sitemap():
    xml = '''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://compress-kit.onrender.com/</loc>
    <lastmod>2026-06-03</lastmod>
    <changefreq>monthly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>'''
    return Response(xml, mimetype='application/xml')

@app.route('/robots.txt')
def robots():
    content = '''User-agent: *
Allow: /
Sitemap: https://compress-kit.onrender.com/sitemap.xml'''
    return Response(content, mimetype='text/plain')


if __name__ == '__main__':
    app.run(debug=False)