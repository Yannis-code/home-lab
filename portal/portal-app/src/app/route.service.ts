import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ServiceRoute } from './route.model';

@Injectable({ providedIn: 'root' })
export class RouteService {
  private readonly http = inject(HttpClient);

  getRoutes(): Observable<ServiceRoute[]> {
    return this.http.get<ServiceRoute[]>('/api/routes');
  }
}