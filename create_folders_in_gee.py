import ee
ee.Initialize(project='replicating-paper')
ee.data.createAsset({'type': 'FOLDER'}, 'projects/replicating-paper/assets/fmu')
ee.data.createAsset({'type': 'FOLDER'}, 'projects/replicating-paper/assets/fmu/sanjay_van_baseline')
ee.data.createAsset({'type': 'FOLDER'}, 'projects/replicating-paper/assets/fmu/sanjay_van_baseline/masking')