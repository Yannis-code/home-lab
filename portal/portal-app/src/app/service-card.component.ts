import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { ServiceRoute } from './route.model';

@Component({
  selector: 'portal-service-card',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <a class="service" [href]="route().url">
      <div class="service-content">
        <h2>{{ route().name }}</h2>
        <p>{{ route().description }}</p>
        <div class="badges" aria-label="Protection status">
          @for (method of route().auth; track method) {
            <span class="status-badge" [class]="method">{{ authLabel(method) }}</span>
          }
        </div>
      </div>
      <span class="arrow" aria-hidden="true"><span>&#8599;</span></span>
    </a>
  `,
})
export class ServiceCardComponent {
  readonly route = input.required<ServiceRoute>();

  authLabel(method: string): string {
    return {
      basic: 'Basic auth',
      integrated: 'App Auth',
      public: 'Public',
      sso: 'SSO',
    }[method] ?? method;
  }
}