from app import create_app
import os

app = create_app()

# Production: gunicorn -w 4 -b 0.0.0.0:$PORT run:app

if __name__ == '__main__':
    # Development server
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
