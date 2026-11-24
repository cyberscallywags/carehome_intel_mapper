import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { environment } from '../../environments/environment';

import type { CareHome, CareHomePage, Health, Item, Session, Site } from './api.types';

// The API's shapes, generated from src/app/models.py by `uv run task types`; import them from here.
export type * from './api.types';

/** A care home search: every part that is filled in must match. */
export interface CareHomeSearch {
  name: string;
  location: string;
  postcode: string;
  ratings: CareHome['rating'][];
}

function searchParams(search: CareHomeSearch): HttpParams {
  let params = new HttpParams();
  for (const key of ['name', 'location', 'postcode'] as const) {
    const value = search[key].trim();
    if (value) params = params.set(key, value);
  }
  for (const rating of search.ratings) params = params.append('rating', rating);
  return params;
}

/** The app's only way to reach data: HTTP to the API, never Neo4j. */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiUrl;

  health(): Observable<Health> {
    return this.http.get<Health>(`${this.base}/health`);
  }

  site(): Observable<Site> {
    return this.http.get<Site>(`${this.base}/site`);
  }

  listItems(limit = 100): Observable<Item[]> {
    return this.http.get<Item[]>(`${this.base}/items`, { params: { limit } });
  }

  createItem(name: string): Observable<Item> {
    return this.http.post<Item>(`${this.base}/items`, { name });
  }

  /** Care homes matching a search, in name order, with the total number of matches. */
  searchCareHomes(search: CareHomeSearch, limit = 50): Observable<CareHomePage> {
    const params = searchParams(search).set('limit', limit);
    return this.http.get<CareHomePage>(`${this.base}/carehomes`, { params });
  }

  /** Address of the API's map page for a search, to show in a frame; `focus` opens one home. */
  careHomeMapUrl(search: CareHomeSearch, focus?: string | null): string {
    let params = searchParams(search);
    if (focus) params = params.set('focus', focus);
    const query = params.toString();
    return `${this.base}/carehomes/map${query ? `?${query}` : ''}`;
  }

  /** GET an entity's list, e.g. `/volunteers`, for pages added with `uv run task new_entity`. */
  list<T>(path: string): Observable<T[]> {
    return this.http.get<T[]>(`${this.base}${path}`);
  }

  /** POST a new entity to its list path. */
  create<T>(path: string, body: unknown): Observable<T> {
    return this.http.post<T>(`${this.base}${path}`, body);
  }

  login(email: string, password: string): Observable<Session> {
    return this.http.post<Session>(`${this.base}/auth/login`, { email, password });
  }
}
