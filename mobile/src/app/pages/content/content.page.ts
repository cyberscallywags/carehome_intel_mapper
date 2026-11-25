import { Component, computed, effect, inject, input } from '@angular/core';
import {
  IonButton,
  IonButtons,
  IonContent,
  IonHeader,
  IonMenuButton,
  IonText,
  IonTitle,
  IonToolbar,
} from '@ionic/angular';

import meta from '../../core/meta.json';
import { SiteStore } from '../../core/site.store';
import { SectionsComponent } from '../../shared/sections.component';

/**
 * One template for every manifest page: /welcome and /about pass their slug as route data,
 * sidebar pages arrive as /p/:slug. Adding a page means adding it to site.json, not code.
 */
import { AccountMenuComponent } from '../../shared/account-menu.component';

@Component({
  selector: 'app-content',
  templateUrl: 'content.page.html',
  styleUrls: ['content.page.scss'],
  imports: [
    AccountMenuComponent,
    IonButton,
    IonButtons,
    IonContent,
    IonHeader,
    IonMenuButton,
    IonText,
    IonTitle,
    IonToolbar,
    SectionsComponent,
  ],
})
export class ContentPage {
  private readonly store = inject(SiteStore);

  /** The brand mark, copied into assets/brand by `uv run task sync`. */
  protected readonly mark = meta.mark;
  /** The brand hero, if it has one: shown above the welcome page in place of the mark. */
  protected readonly hero = meta.hero;
  protected readonly heroAlt = meta.hero_alt;

  readonly slug = input.required<string>();
  readonly brand = computed(() => this.store.site().brand);
  readonly page = computed(() => this.store.page(this.slug()));

  constructor() {
    effect(() => this.store.pageTitle.set(this.page()?.title ?? null));
  }
}
