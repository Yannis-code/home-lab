import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { AsyncPipe } from '@angular/common';
import { catchError, of, startWith } from 'rxjs';
import { RouteService } from './route.service';
import { ServiceCardComponent } from './service-card.component';

@Component({
  selector: 'portal-root',
  standalone: true,
  imports: [AsyncPipe, ServiceCardComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <main>
      <header>
        <h1>Services</h1>
        <p class="header-subtitle">doudou.house</p>
      </header>

      @if (routes$ | async; as routes) {
        <section class="services" aria-label="Home lab services">
          @for (route of routes; track route.host + route.path) {
            <portal-service-card [route]="route" />
          } @empty {
            <p class="empty">No routed services are available right now.</p>
          }
        </section>
      }
    </main>
  `,
})
export class AppComponent {
  private readonly routeService = inject(RouteService);
  readonly routes$ = this.routeService.getRoutes().pipe(
    catchError(() => of([])),
    startWith([]),
  );
}