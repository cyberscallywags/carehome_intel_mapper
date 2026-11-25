import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../environments/environment';
import { ApiService } from './api.service';

describe('ApiService', () => {
  let api: ApiService;
  let http: HttpTestingController;
  const base = environment.apiUrl;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    api = TestBed.inject(ApiService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('reads health from /health', () => {
    let body: unknown;
    api.health().subscribe((h) => (body = h));
    http.expectOne(`${base}/health`).flush({ status: 'ok', env: 'test', neo4j: true });
    expect(body).toEqual({ status: 'ok', env: 'test', neo4j: true });
  });

  it('searches care homes with every filled-in field and each rating', () => {
    const search = { name: ' ty ', location: '', postcode: 'SA73', ratings: ['Good', 'Outstanding'] as const };
    api.searchCareHomes({ ...search, ratings: [...search.ratings] }, 20).subscribe();
    const req = http.expectOne((r) => r.url === `${base}/carehomes`);
    expect(req.request.params.toString()).toBe('name=ty&postcode=SA73&rating=Good&rating=Outstanding&limit=20');
    req.flush({ total: 0, items: [] });
  });

  it('builds the map address for a search and a focused home', () => {
    const everything = { name: '', location: '', postcode: '', ratings: [] };
    expect(api.careHomeMapUrl(everything)).toBe(`${base}/carehomes/map`);
    expect(api.careHomeMapUrl({ ...everything, location: 'Milford Haven' }, '1-101')).toBe(
      `${base}/carehomes/map?location=Milford%20Haven&focus=1-101`,
    );
  });
});
