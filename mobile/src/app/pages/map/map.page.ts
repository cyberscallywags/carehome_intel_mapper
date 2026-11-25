import { HttpErrorResponse } from '@angular/common/http';
import { Component, HostListener, OnInit, computed, inject, signal } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
import { DomSanitizer } from '@angular/platform-browser';
import {
  IonButton,
  IonButtons,
  IonCheckbox,
  IonContent,
  IonHeader,
  IonIcon,
  IonInput,
  IonItem,
  IonLabel,
  IonList,
  IonListHeader,
  IonMenuButton,
  IonNote,
  IonText,
  IonTitle,
  IonToolbar,
} from '@ionic/angular';

import { ApiService, CareHome, CareHomePage, CareHomeSearch } from '../../core/api.service';
import { SiteStore } from '../../core/site.store';

type Rating = CareHome['rating'];

/** One colour and letter per rating; the same as the map's markers (app.carehomes in the API). */
export const RATINGS: { name: Rating; colour: string; initial: string }[] = [
  { name: 'Outstanding', colour: '#1d4ed8', initial: 'O' },
  { name: 'Good', colour: '#15803d', initial: 'G' },
  { name: 'Requires improvement', colour: '#b45309', initial: 'R' },
  { name: 'Inadequate', colour: '#b91c1c', initial: 'I' },
  { name: 'Not rated', colour: '#4b5563', initial: '–' },
];

const EVERYTHING: CareHomeSearch = { name: '', location: '', postcode: '', ratings: [] };

/**
 * The care home map with a search side menu. On a phone the menu slides in over the map from
 * the end side; on a wide screen it stays open beside it. It is plain markup, not an ion-menu:
 * Ionic turns every menu inside the app's split pane into a fixed pane on wide screens, where
 * it can no longer be opened. The map itself is the API's Folium page in a frame, so it is the
 * same map the web UI shows.
 */
@Component({
  selector: 'app-map',
  templateUrl: 'map.page.html',
  styleUrls: ['map.page.scss'],
  imports: [
    ReactiveFormsModule,
    IonButton,
    IonButtons,
    IonCheckbox,
    IonContent,
    IonHeader,
    IonIcon,
    IonInput,
    IonItem,
    IonLabel,
    IonList,
    IonListHeader,
      IonMenuButton,
    IonNote,
    IonText,
    IonTitle,
    IonToolbar,
  ],
})
export class MapPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly store = inject(SiteStore);
  private readonly sanitizer = inject(DomSanitizer);

  protected readonly ratings = RATINGS;

  /** The search the map is showing; the form only becomes this on Search. */
  readonly applied = signal<CareHomeSearch>(EVERYTHING);
  /** `location_id` of the home the map is centred on, if one was picked from the list. */
  readonly focus = signal<string | null>(null);
  readonly page = signal<CareHomePage | null>(null);
  readonly error = signal<string | null>(null);
  /** Whether the menu is slid in; only matters on narrow screens, where it starts closed. */
  readonly searchOpen = signal(false);

  // Built only from the API's own address and encoded search fields, so it is safe to frame.
  readonly mapUrl = computed(() =>
    this.sanitizer.bypassSecurityTrustResourceUrl(
      this.api.careHomeMapUrl(this.applied(), this.focus()),
    ),
  );
  readonly isSample = computed(() => this.page()?.dataset?.source === 'sample');

  readonly form = new FormGroup({
    name: new FormControl('', { nonNullable: true }),
    location: new FormControl('', { nonNullable: true }),
    postcode: new FormControl('', { nonNullable: true }),
    ratings: new FormGroup(
      Object.fromEntries(
        RATINGS.map((r) => [r.name, new FormControl(false, { nonNullable: true })]),
      ) as Record<Rating, FormControl<boolean>>,
    ),
  });

  ngOnInit(): void {
    this.store.pageTitle.set('Map');
    this.load();
  }

  search(): void {
    const { name, location, postcode, ratings } = this.form.getRawValue();
    this.applied.set({
      name: name.trim(),
      location: location.trim(),
      postcode: postcode.trim(),
      ratings: RATINGS.map((r) => r.name).filter((r) => ratings[r]),
    });
    this.focus.set(null);
    this.load();
    this.closeSearch();
  }

  clear(): void {
    this.form.reset();
    this.search();
  }

  /** Centre the map on one home from the list and open its details. */
  show(home: CareHome): void {
    this.focus.set(home.location_id);
    this.closeSearch();
  }

  openSearch(): void {
    this.searchOpen.set(true);
  }

  @HostListener('document:keydown.escape')
  closeSearch(): void {
    this.searchOpen.set(false);
  }

  protected colour(rating: Rating): string {
    return RATINGS.find((r) => r.name === rating)?.colour ?? '#4b5563';
  }

  protected initial(rating: Rating): string {
    return RATINGS.find((r) => r.name === rating)?.initial ?? '–';
  }

  private load(): void {
    this.error.set(null);
    this.api.searchCareHomes(this.applied()).subscribe({
      next: (page) => this.page.set(page),
      error: (err: HttpErrorResponse) => {
        this.page.set(null);
        this.error.set(err.status ? `API error ${err.status}` : 'API unreachable');
      },
    });
  }
}
