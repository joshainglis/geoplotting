from distutils.core import setup

setup(
    name='isea_interviz',
    version='0.0.1-dev',
    packages=[
        'interviz'
    ],
    url='',
    license='',
    author='joshainglis',
    author_email='joshainglis@gmail.com',
    description='',
    requires=[
        'click',
        'fiona',
        'geopandas',
        'numpy',
        'rasterio',
    ],
    entry_points="""
    [console_scripts]
    interviz-vs2poly = interviz:generate_viewshed_polygons
    interviz-spatial-join = interviz:spatial_join
    """,
)
