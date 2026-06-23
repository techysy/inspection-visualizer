from app_factory import create_app

app = create_app()
app.run(debug=False, host='127.0.0.1', port=5001)
