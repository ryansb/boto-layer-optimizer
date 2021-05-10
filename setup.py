import setuptools

with open("README.md") as fp:
    long_description = fp.read()


setuptools.setup(
    name="lambda_layers_testing",
    version="0.0.1",
    description="Constructs for creating optimized Lambda layers for boto3/botocore",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="author",
    package_dir={"": "lambda_layers_testing"},
    packages=setuptools.find_packages(where="lambda_layers_testing"),
    install_requires=[
        "aws-cdk-lib==2.0.0-rc.1",
        "constructs>=10.0.0,<11.0.0",
    ],
    python_requires=">=3.6",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.8",
        "Topic :: Software Development :: Code Generators",
        "Topic :: Utilities",
        "Typing :: Typed",
    ],
)
