def test_top_3200_page_loads(client):
    response = client.get('/top-3200')
    assert response.status_code == 200
    assert b'3200' in response.data
