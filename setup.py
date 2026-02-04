import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="pytransportnswv2",
    version="2.2.5",
    author="andystewart999",
    author_email="andy.stewart@live.com",
    description="Get detailed per-trip transport information from TransportNSW",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/andystewart999/TransportNSWv2",
    packages=setuptools.find_packages(),
    install_requires=[
        'gtfs-realtime-bindings'
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
