from backend import create_app
import frontend

app = create_app()


if __name__ == '__main__':
    app.run(debug=True)
