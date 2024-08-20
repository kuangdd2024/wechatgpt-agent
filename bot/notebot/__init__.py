"""
部署好服务，模拟操作。
"""
import json
import pprint

import requests
import tqdm


def run_load_data():
    """
    模拟跑管理员上传数据。
    """
    manage_api = 'http://localhost:8000/manage'
    _index = 'cmedqa2'

    data_path = 'wp/cmedqa2.json'
    data = json.load(open(data_path, encoding='utf8'))
    for num, dt in enumerate(tqdm.tqdm(data)):
        content = dt['question']
        _source = json.dumps(dict(answer=dt['answer']))
        _id = f'{_index}_{num + 10000}'
        flag = requests.post(manage_api,
                             params=dict(_index=_index, _id=_id, content=content, _source=_source))
        pprint.pprint(dt)
        pprint.pprint(flag.json())
        print('#' * 100)
        if num >= 10:
            break


def run_search():
    """
    模拟跑用户搜索。
    """
    search_api = 'http://localhost:8000/search'
    _index = 'cmedqa2'

    data_path = 'wp/cmedqa2.json'
    data = json.load(open(data_path, encoding='utf8'))
    for num, dt in enumerate(tqdm.tqdm(data)):
        query = dt['question']
        response = requests.post(search_api,
                                 params=dict(_index=_index, query=query))
        pprint.pprint(dt)
        pprint.pprint(response.json())
        print('#' * 100)
        if num >= 10:
            break


if __name__ == "__main__":
    # run_load_data()
    # run_search()
    flag = requests.post('http://localhost:8000/manage',
                         params=dict(_index='tmp', _id='tmp2', content='你好！', _source='{"answer": "回复"}'))
    pprint.pprint(flag.json())
    flag = {'f_flags': [None], 'k_flags': [None]}
    flag = {'f_flags': [{'_id': '=A0K1r_Hhm_qqYE4mUnjjFw=',
                         '_index': 'f_tmp',
                         '_primary_term': 17,
                         '_seq_no': 12,
                         '_shards': {'failed': 0, 'successful': 1, 'total': 2},
                         '_version': 6,
                         'result': 'updated'}],
            'k_flags': [{'_id': 'tmp2',
                         '_index': 'k_tmp',
                         '_primary_term': 17,
                         '_seq_no': 2,
                         '_shards': {'failed': 0, 'successful': 1, 'total': 2},
                         '_version': 1,
                         'result': 'created'}]}

    response = requests.post('http://localhost:8000/search',
                             params=dict(_index='tmp', query='邝'))
    pprint.pprint(response.json())
    result = [{'_id': 'tmp_i',
               '_index': 'k_tmp',
               '_score': 0.88020796,
               '_source': {'content': ['你好！', '这是智能搜索引擎。']}},
              {'_id': 'tmp',
               '_index': 'k_tmp',
               '_score': 0.8625487,
               '_source': {'content': ['你好']}}]
