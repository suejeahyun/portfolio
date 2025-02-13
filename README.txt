conda create -n papercup python=3.8 -y
conda activate papercup
pip install --no-cache-dir --upgrade -r requirements.txt
flask run --debug
