from flask import Flask, request, jsonify, send_file, render_template
from compressor import compress_image
from io import BytesIO
from flask import render_template



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
    # Check file was uploaded
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'error': 'File type not supported'}), 400

    # Get target size from form data
    try:
        target_min = int(request.form.get('target_min', 17))
        target_max = int(request.form.get('target_max', 20))
    except ValueError:
        return jsonify({'error': 'Invalid target size'}), 400

    # Run compression
    result_bytes, original_kb, final_kb, success = compress_image(
        file, target_min, target_max
    )

    # Send compressed file back
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

    # Add size info in headers so frontend can read it
    response.headers['X-Original-KB'] = str(original_kb)
    response.headers['X-Final-KB'] = str(final_kb)
    response.headers['X-Success'] = str(success)

    return response


if __name__ == '__main__':
    app.run(debug=True)