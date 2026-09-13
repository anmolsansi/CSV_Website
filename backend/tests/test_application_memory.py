"""Acceptance regressions for persistent application history and batch candidates."""
import uuid

import pytest
from app.models import CsvRow, JobTrack, User


@pytest.fixture
def memory_user(client, db_session):
    email = f"memory-{uuid.uuid4()}@example.test"
    assert client.post('/auth/dev-login', json={'email': email}).status_code == 200
    user = db_session.query(User).filter_by(email=email).one()
    return client, db_session, user


def add_rows(db, user, count=8):
    rows = [CsvRow(user_id=user.id, upload_batch_id='memory-test',
                   url=f'https://example.test/{uuid.uuid4()}', title=f'Job {i:02}',
                   company_guess=' Acme ', ats_group='greenhouse', location_group='remote')
            for i in range(count)]
    db.add_all(rows)
    db.commit()
    return rows


def test_visits_are_independent_of_applications(memory_user):
    client, db, user = memory_user
    rows = add_rows(db, user, 3)
    client.post('/crm/from-rows/bulk', json={'row_ids': [rows[0].id], 'status': 'applied'})
    client.post(f'/rows/{rows[1].id}/click')
    unopened = client.get('/rows', params={'unopened_only': True}).json()['rows']
    assert {r['id'] for r in unopened} == {rows[0].id, rows[2].id}
    opened = client.get('/rows', params={'opened_only': True}).json()['rows']
    assert [r['id'] for r in opened] == [rows[1].id]
    assert client.get('/rows', params={'unopened_only': True, 'opened_only': True}).json()['rows'] == []


def test_global_filtered_top_five_and_next_batch(memory_user):
    client, db, user = memory_user
    rows = add_rows(db, user, 60)
    rows[0].clicked = True
    rows[1].location_group = 'onsite'
    rows[2].url = 'javascript:alert(1)'
    db.commit()
    params = dict(unopened_only=True, openable_only=True, location_group='remote',
                  ats_group='greenhouse', sort_by='title', sort_dir='asc', page=1, page_size=5)
    first = client.get('/rows', params=params).json()['rows']
    assert [r['data']['title'] for r in first] == [f'Job {i:02}' for i in range(3, 8)]
    for row in first:
        assert client.post(f"/rows/{row['id']}/click").status_code == 200
    second = client.get('/rows', params=params).json()['rows']
    assert [r['data']['title'] for r in second] == [f'Job {i:02}' for i in range(8, 13)]


def test_mark_applied_is_atomic_and_idempotent(memory_user):
    client, db, user = memory_user
    rows = add_rows(db, user, 2)
    payload = {'row_ids': [rows[1].id, rows[1].id], 'status': 'applied'}
    first = client.post('/crm/from-rows/bulk', json=payload)
    assert first.status_code == 200
    assert first.json()['created'] == 1
    app_id = first.json()['application_ids'][0]
    track = db.get(JobTrack, app_id)
    assert track.csv_row_id == rows[1].id
    assert track.applied_at is not None
    date = track.applied_at
    assert client.post('/crm/from-rows/bulk', json=payload).json()['created'] == 0
    client.patch(f'/crm/applications/{app_id}', json={'status': 'interview'})
    client.patch(f'/crm/applications/{app_id}', json={'status': 'applied'})
    db.expire_all()
    assert db.get(JobTrack, app_id).applied_at == date
    assert db.query(JobTrack).filter_by(user_id=user.id).count() == 1
    assert not db.get(CsvRow, rows[1].id).clicked


def test_bulk_foreign_rows_rejected_without_partial_writes(memory_user):
    client, db, user = memory_user
    rows = add_rows(db, user, 1)
    other = User(email=f'other-{uuid.uuid4()}@example.test')
    db.add(other)
    db.commit()
    foreign = add_rows(db, other, 1)[0]
    resp = client.post('/crm/from-rows/bulk', json={'row_ids': [rows[0].id, foreign.id], 'status': 'applied'})
    assert resp.status_code == 404
    assert db.query(JobTrack).filter_by(user_id=user.id).count() == 0
    assert client.post('/crm/from-rows/bulk', json={'row_ids': [rows[0].id], 'status': 'garbage'}).status_code == 422
    assert client.post(f'/rows/{foreign.id}/click').status_code == 404


def test_deleting_csv_retains_job_and_company(memory_user):
    client, db, user = memory_user
    rows = add_rows(db, user, 1)
    row_id = rows[0].id
    result = client.post('/crm/from-rows/bulk', json={'row_ids': [row_id], 'status': 'applied'}).json()
    assert client.request('DELETE', '/rows', json={'row_ids': [row_id]}).status_code == 200
    db.expire_all()
    track = db.get(JobTrack, result['application_ids'][0])
    assert track.csv_row_id is None
    assert track.title == 'Job 00' and track.applied_at
    companies = client.get('/crm/companies').json()
    assert companies['companies'] == [{'company': 'Acme', 'total': 1, 'applied': 1}]
    assert client.get('/crm/companies/acme').json()['roles'][0]['track_id'] == track.id


def test_company_directory_normalization_pagination_and_isolation(memory_user):
    client, db, user = memory_user
    rows = add_rows(db, user, 4)
    rows[1].company_guess = 'acme'
    rows[2].company_guess = 'Beta'
    rows[3].company_guess = None
    db.commit()
    client.post('/crm/from-rows/bulk', json={'row_ids': [r.id for r in rows], 'status': 'applied'})
    data = client.get('/crm/companies', params={'page_size': 1}).json()
    assert data['total_count'] == 3 and data['has_next']
    assert data['companies'][0]['total'] == 2
    assert client.get('/crm/companies', params={'q': 'ACME'}).json()['total_count'] == 1
    assert client.get('/crm/companies', params={'q': '%'}).json()['total_count'] == 0
    assert client.get('/crm/companies', params={'page': 99}).json()['companies'] == []
    assert client.get('/crm/companies/Unknown%20company').json()['total'] == 1
    client.post('/auth/dev-login', json={'email': f'isolated-{uuid.uuid4()}@example.test'})
    assert client.get('/crm/companies').json()['companies'] == []
    assert client.get('/crm/companies/acme').json()['roles'] == []


def test_company_directory_requires_auth(client):
    client.post('/auth/logout')
    assert client.get('/crm/companies').status_code == 401


def test_company_names_with_slashes(memory_user):
    client, db, user = memory_user
    rows = add_rows(db, user, 1)
    rows[0].company_guess = 'Acme / Labs'
    db.commit()
    client.post('/crm/from-rows/bulk', json={'row_ids': [rows[0].id], 'status': 'applied'})
    response = client.get('/crm/companies/Acme%20%2F%20Labs')
    assert response.status_code == 200
    assert response.json()['applied'] == 1
