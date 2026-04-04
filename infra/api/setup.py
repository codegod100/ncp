from setuptools import setup
setup(
    name='nix-fly-api',
    version='1.0.0',
    py_modules=['main'],
    install_requires=['fastapi>=0.104.0', 'uvicorn[standard]>=0.24.0', 'pydantic>=2.5.0', 'python-dotenv>=1.0.0'],
    entry_points={'console_scripts': ['nix-fly-api=main:main']},
)
