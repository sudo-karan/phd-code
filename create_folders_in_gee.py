import ee

ee.Initialize(project='replicating-paper')

folders = [
    'projects/replicating-paper/assets/fmu',
    'projects/replicating-paper/assets/fmu/sanjay_van_baseline',
    'projects/replicating-paper/assets/fmu/sanjay_van_baseline/masking',
    'projects/replicating-paper/assets/fmu/sanjay_van_baseline/data_load',
]

for path in folders:
    try:
        ee.data.createAsset({'type': 'FOLDER'}, path)
        print(f"Created: {path}")
    except ee.EEException as e:
        msg = str(e).lower()
        if 'already exists' in msg or 'cannot overwrite' in msg:
            print(f"Exists:  {path}")
        else:
            raise