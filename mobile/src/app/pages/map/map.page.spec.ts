import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpErrorResponse } from '@angular/common/http';
import { of, throwError } from 'rxjs';

import { ApiService, CareHome, CareHomePage, CareHomeSearch } from '../../core/api.service';
import { MapPage } from './map.page';

const home: CareHome = {
  location_id: '1-101',
  name: 'Ty Example',
  address: '1 Example Street',
  town: 'Bristol',
  county: '',
  postcode: 'BS1 9ZZ',
  local_authority: 'Bristol, City of',
  region: 'South West',
  latitude: 51.45,
  longitude: -2.59,
  rating: 'Good',
  service_types: [],
  phone: '',
  website: '',
  provider_id: '',
  provider_name: '',
};

const found = (source: 'sample' | 'cqc-directory' = 'cqc-directory'): CareHomePage => ({
  total: 1,
  items: [home],
  dataset: { source, name: 'directory.ods', loaded_at: '2026-11-02T00:00:00Z', count: 1 },
});

function setup(search = vi.fn(() => of(found()))) {
  const api = {
    searchCareHomes: search,
    careHomeMapUrl: vi.fn(
      (s: CareHomeSearch, focus?: string | null) =>
        `/api/carehomes/map?name=${s.name}&focus=${focus ?? ''}`,
    ),
  };
  TestBed.configureTestingModule({
    imports: [MapPage],
    providers: [{ provide: ApiService, useValue: api }],
  });
  const fixture: ComponentFixture<MapPage> = TestBed.createComponent(MapPage);
  fixture.detectChanges();
  const isOpen = () => fixture.nativeElement.querySelector('.layout').classList.contains('open');
  return { fixture, page: fixture.componentInstance, api, isOpen };
}

describe('MapPage', () => {
  it('frames the whole map and lists the homes', () => {
    const { fixture, api } = setup();
    const frame: HTMLIFrameElement = fixture.nativeElement.querySelector('iframe.map');
    expect(frame.getAttribute('src')).toBe('/api/carehomes/map?name=&focus=');
    expect(api.searchCareHomes).toHaveBeenCalledWith({ name: '', location: '', postcode: '', ratings: [] });
    expect(fixture.nativeElement.querySelector('[data-testid=count]').textContent).toContain('1 care home');
    expect(fixture.nativeElement.querySelector('[data-testid=results]').textContent).toContain('Ty Example');
  });

  it('searches by name, location, postcode and rating, then closes the menu', () => {
    const { fixture, page, api, isOpen } = setup();
    page.openSearch();
    page.form.patchValue({ name: ' ty ', location: 'Bristol', postcode: 'bs1' });
    page.form.controls.ratings.controls['Good'].setValue(true);
    const form: HTMLFormElement = fixture.nativeElement.querySelector('form');
    const submit = new Event('submit', { cancelable: true });
    form.dispatchEvent(submit);
    fixture.detectChanges();
    const search = { name: 'ty', location: 'Bristol', postcode: 'bs1', ratings: ['Good'] };
    expect(submit.defaultPrevented).toBe(true);
    expect(api.searchCareHomes).toHaveBeenLastCalledWith(search);
    expect(api.careHomeMapUrl).toHaveBeenLastCalledWith(search, null);
    expect(isOpen()).toBe(false);
  });

  it('centres the map on a home picked from the list', () => {
    const { fixture, page, api, isOpen } = setup();
    page.openSearch();
    fixture.nativeElement.querySelector('[data-testid=results] ion-item').click();
    fixture.detectChanges();
    expect(api.careHomeMapUrl).toHaveBeenLastCalledWith(expect.anything(), '1-101');
    expect(fixture.nativeElement.querySelector('iframe.map').getAttribute('src')).toContain('focus=1-101');
    expect(isOpen()).toBe(false);
  });

  it('clears the search', () => {
    const { page, api } = setup();
    page.form.patchValue({ name: 'ty' });
    page.search();
    page.clear();
    expect(page.form.getRawValue().name).toBe('');
    expect(api.searchCareHomes).toHaveBeenLastCalledWith({ name: '', location: '', postcode: '', ratings: [] });
  });

  it('opens the search menu from the toolbar and closes it with Escape or the backdrop', () => {
    const { fixture, isOpen } = setup();
    const toggle: HTMLElement = fixture.nativeElement.querySelector('[data-testid=open-search]');
    expect(isOpen()).toBe(false);
    toggle.click();
    fixture.detectChanges();
    expect(isOpen()).toBe(true);
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    fixture.detectChanges();
    expect(isOpen()).toBe(false);
    toggle.click();
    fixture.nativeElement.querySelector('.backdrop').click();
    fixture.detectChanges();
    expect(isOpen()).toBe(false);
  });

  it('says when the homes are made-up sample data', () => {
    const { fixture } = setup(vi.fn(() => of(found('sample'))));
    expect(fixture.nativeElement.querySelector('[data-testid=sample]').textContent).toContain('made up');
  });

  it('reports an unreachable API', () => {
    const { fixture } = setup(vi.fn(() => throwError(() => new HttpErrorResponse({ status: 0 }))));
    expect(fixture.nativeElement.querySelector('[role=alert]').textContent).toContain('API unreachable');
  });
});
