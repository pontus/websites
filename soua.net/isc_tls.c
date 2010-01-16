/*
** isc_tls.c                          Routines to handle TLS
**
** Copyright (C) 2005 by Pontus Freyhult
**
**
** This library is free software; you can redistribute it and/or
** modify it under the terms of the GNU Library General Public
** License as published by the Free Software Foundation; either
** version 2 of the License, or (at your option) any later version.
**
** This library is distributed in the hope that it will be useful,
** but WITHOUT ANY WARRANTY; without even the implied warranty of
** MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
** Library General Public License for more details.
**
** You should have received a copy of the GNU Library General Public
** License along with this library; if not, write to the Free
** Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
**
** (See ChangeLog for recent history)
*/

#include <errno.h>
#ifdef HAVE_STDLIB_H
#  include <stdlib.h>
#endif
#ifdef HAVE_STDDEF_H
#  include <stddef.h>
#endif
#ifdef HAVE_STDARG_H
#  include <stdarg.h>
#endif
#include <ctype.h>
#include <sys/types.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <netdb.h>
#ifdef HAVE_STRING_H
#  include <string.h>
#endif
#include <fcntl.h>
#ifndef NULL
#  include <stdio.h>
#endif
#ifdef HAVE_UNISTD_H
#  include <unistd.h>
#endif
#include <time.h>
#include <assert.h>

#ifdef HAVE_GNUTLS
#include <gnutls/gnutls.h>
#endif

#include "oop.h"
#include "adns.h"
#include "oop-adns.h"

#include "s-string.h"

#include "isc.h"
#include "intern.h"
#include "isc_addr.h"
#include "unused.h"

static int dh_bits = 1024;
static int cert_req = 0;
static double handshake_timeout = 4;
static int dh_regenerate_every = 1024;
static char* certfile = NULL;
static char* cafile = NULL;
static char* keyfile = NULL;
static char* crlfile = NULL;


static int mcb_count = 0;

static void
isc_generate_dh_params(struct isc_mcb *mcb)
{
#ifdef HAVE_GNUTLS
  int ret = gnutls_dh_params_generate2(mcb->dh_params, dh_bits);
  if (ret<0) 
      fprintf(stderr, "TLS Failed to generate DH params (%s), ignoring.\n",
	      gnutls_strerror(ret));

  gnutls_certificate_set_dh_params(mcb->x509_cred, mcb->dh_params);
  gnutls_anon_set_server_dh_params(mcb->anoncred, mcb->dh_params);
#endif
}

static size_t
isc_tls_no_func(struct isc_scb* scb, void* buf, size_t count)
{
  return EWOULDBLOCK;
}

static size_t
isc_tls_read(struct isc_scb* scb, void* buf, size_t count)
{
  struct isc_scb_internal *sci = (struct isc_scb_internal*) scb; 
  int ret = gnutls_record_recv(sci->tls_session, buf, count);

  if (ret == GNUTLS_E_AGAIN)
    errno = EAGAIN;
  if (ret == GNUTLS_E_INTERRUPTED)
    errno = EINTR;

  return ret;
}

static size_t
isc_tls_write(struct isc_scb* scb, void* buf, size_t count)
{
  struct isc_scb_internal *sci = (struct isc_scb_internal*) scb;
  int ret = gnutls_record_send(sci->tls_session, buf, count);

  if (ret == GNUTLS_E_AGAIN)
    errno = EAGAIN;
  if (ret == GNUTLS_E_INTERRUPTED)
    errno = EINTR;

  return ret;
}

static void 
isc_tls_regenerate(struct isc_mcb* mcb)
{
  /* FIXME: Should we deinit and init here? */
  /* gnutls_dh_params_deinit(mcb->dh_params); */
  isc_generate_dh_params(mcb);
  mcb->dh_params_use_count = 0;
}

int 
isc_tls_support()
{
#ifndef HAVE_GNUTLS
  return 0;
#else
  return 1;
#endif
}

int 
isc_sasl_support()
{
  return 0;
}



static void*
isc_tls_negotiate_callback(oop_source* source,
			   struct timeval UNUSED(tv), 
			   void *data)
{
  struct isc_scb_internal *sci = (struct isc_scb_internal*)data;
  
#ifdef HAVE_GNUTLS

  int ret = gnutls_handshake(sci->tls_session);

  /* FIXME? The server will be locked until we finish the handshake
   * or abort because of timeout.
   */

  if (ret>=0)
    {
      unsigned int certstat = 0;
      
      if (cert_req)
	certstat = gnutls_certificate_verify_peers(sci->tls_session);

      if (certstat & ( GNUTLS_CERT_INVALID |
		       GNUTLS_CERT_SIGNER_NOT_FOUND |
		       GNUTLS_CERT_REVOKED ))
	fprintf( stderr, 
		 "TLS client cetificate verification requested and client\n"
		 "certificate is not valid (%s).\n",
		 gnutls_strerror(certstat));
      else
	{
	  sci->read_func = &isc_tls_read;
	  sci->write_func = &isc_tls_write;
	}
    }
  else
    {
      if ((ret == GNUTLS_E_AGAIN ||
	   ret == GNUTLS_E_INTERRUPTED ))
	{
	  if((time(NULL) - sci->tls_handshake_begin) 
	     < handshake_timeout) 
	    {
	      struct timeval at;
	      int timeerr = gettimeofday(&at, NULL);
	      
	      if (timeerr)
		{
		  perror("gettimeofday failed");
		  source->on_time(source, 
				  OOP_TIME_NOW,
				  isc_tls_negotiate_callback,
				  data);	  
		}	      
	      else
		{
		  at.tv_sec ++; /* Wait a little before */
		  source->on_time(source, 
				  at,
				  isc_tls_negotiate_callback,
				  data);	  
		}
	    }
	  else /* No time left */
	    {
	      fprintf(stderr, "TLS negotiation timed out.\n");

	      sci->read_func = NULL;
	      sci->write_func = NULL;
	      
	    }
	} /* Another error? */
      else
	{
	  fprintf(stderr, "TLS negotiation failed: %s\n",
		  gnutls_strerror(ret));
	  
	  sci->read_func = NULL;
	  sci->write_func = NULL;
	}
    }
#endif
  return OOP_CONTINUE;
}


int 
isc_tls_negotiate(struct isc_scb *scb)
{
  int ret = -1;
#ifdef HAVE_GNUTLS
  struct isc_scb_internal *sci = (struct isc_scb_internal*)scb;
  const int kx_prio[] = { GNUTLS_KX_ANON_DH,  GNUTLS_KX_RSA, GNUTLS_KX_DHE_DSS,
        GNUTLS_KX_DHE_RSA, GNUTLS_KX_RSA_EXPORT,  0 };

  if (sci->tls_active) /* Already active, don't mess up */
    return 0;

  sci->tls_active = 1;

  if (scb->master->dh_params_use_count > dh_regenerate_every)
      isc_tls_regenerate(scb->master);

  scb->master->dh_params_use_count++;

  ret = gnutls_init(&sci->tls_session, GNUTLS_SERVER);


  if (ret<0) /* Give up? */
    {
      fprintf(stderr, "TLS initialization failed (%s) giving up.\n",
	      gnutls_strerror(ret));

      return ret;
    }

  ret = gnutls_set_default_priority(sci->tls_session);
  if (ret<0) 
      fprintf(stderr, "TLS Failed to set default priorities (%s), ignoring.\n",
	      gnutls_strerror(ret));


  ret = gnutls_credentials_set(sci->tls_session, GNUTLS_CRD_CERTIFICATE, scb->master->x509_cred);
  if (ret<0) 
      fprintf(stderr, "TLS Failed to add certificate credentials (%s), ignoring.\n",
	      gnutls_strerror(ret));



  ret = gnutls_credentials_set(sci->tls_session, GNUTLS_CRD_ANON, scb->master->anoncred);
  if (ret<0) 
      fprintf(stderr, "TLS Failed to add anonymous credentials (%s), ignoring.\n",
	      gnutls_strerror(ret));

  ret = gnutls_kx_set_priority(sci->tls_session, kx_prio);
  if (ret<0) 
      fprintf(stderr, "TLS Failed to set priorities of key exchange algorithms (%s), ignoring.\n",
	      gnutls_strerror(ret));

  gnutls_dh_set_prime_bits(sci->tls_session, dh_bits);

  if (cert_req)
    gnutls_certificate_server_set_request(sci->tls_session, GNUTLS_CERT_REQUIRE);
  else
    gnutls_certificate_server_set_request(sci->tls_session, GNUTLS_CERT_REQUEST);

  /* Probably not needed */
  /* 
   * gnutls_transport_set_push_function(sci->tls_session,write);
   * gnutls_transport_set_pull_function(sci->tls_session,read);
   */

  gnutls_transport_set_ptr(sci->tls_session, (gnutls_transport_ptr_t) sci->pub.fd);

  sci->tls_handshake_begin = time(NULL);

  fprintf(stderr, "TLS negotiation starting.\n");

  sci->read_func = &isc_tls_no_func; /* Make sure our data are not stolen */


  scb->master->event_source->on_time(scb->master->event_source, 
				     OOP_TIME_NOW, 
				     isc_tls_negotiate_callback,
				     scb);

#endif
  return ret;
}


void 
isc_tls_initialize(struct isc_mcb *mcb)
{
#ifdef HAVE_GNUTLS

  if (!mcb_count)
    gnutls_global_init();

  mcb_count++;

  gnutls_certificate_allocate_credentials(&mcb->x509_cred);

  if (cafile)
    gnutls_certificate_set_x509_trust_file(mcb->x509_cred, cafile,
					   GNUTLS_X509_FMT_PEM);
  
  if (crlfile)
    gnutls_certificate_set_x509_crl_file(mcb->x509_cred, crlfile,
					 GNUTLS_X509_FMT_PEM);
  
  if(keyfile && certfile)
    gnutls_certificate_set_x509_key_file(mcb->x509_cred, certfile, keyfile,
					 GNUTLS_X509_FMT_PEM);

  gnutls_anon_allocate_server_credentials(&mcb->anoncred);  

  gnutls_dh_params_init(&mcb->dh_params);

  isc_tls_regenerate(mcb);
    

#endif /* HAVE_GNUTLS */
}


void 
isc_tls_deinitialize(struct isc_mcb *mcb)
{
#ifdef HAVE_GNUTLS
  /* 
   * FIXME: A (probably theoretical problem)
   * is if there is a problem shutting down a gnutls_session
   * and this gets called before that is completed.
   */

     mcb_count--;

     gnutls_certificate_free_crls(mcb->x509_cred);
     gnutls_certificate_free_cas(mcb->x509_cred);
     gnutls_certificate_free_keys(mcb->x509_cred);
     /* gnutls_certificate_free_ca_names(mcb->x509_cred); */
     gnutls_certificate_free_credentials(mcb->x509_cred);

     gnutls_anon_free_server_credentials(mcb->anoncred);
     
     gnutls_dh_params_deinit(mcb->dh_params);
     
     if (!mcb_count)
       gnutls_global_deinit();    

#endif /* HAVE_GNUTLS */
}

void 
isc_tls_set_params( int dh_bits_param,
		    int cert_req_param,
		    double handshake_timeout_param,
		    int dh_regenerate_every_param,
		    char* certfile_param,
		    char* cafile_param,
		    char* keyfile_param, 
		    char* crlfile_param)
{
  dh_bits = dh_bits_param;
  cert_req = cert_req_param;
  certfile = certfile_param;
  cafile = cafile_param;
  keyfile = keyfile_param;
  crlfile = crlfile_param;
  handshake_timeout = handshake_timeout_param;
  dh_regenerate_every = dh_regenerate_every_param;
} 



static void*
isc_tls_die_callback(oop_source* source,
		     struct timeval UNUSED(tv), 
		     void *data)
{
#ifdef HAVE_GNUTLS
  gnutls_session sess = (gnutls_session) data;

  int ret = gnutls_bye(sess, GNUTLS_SHUT_RDWR);

  if (ret<0) /* Problem? */
    {
      if ((ret  == GNUTLS_E_AGAIN ||
	   ret == GNUTLS_E_INTERRUPTED))
	{
	  source->on_time(source, 
			  OOP_TIME_NOW, 
			  isc_tls_die_callback,
			  data);

	  return OOP_CONTINUE;
	}
      else
	{
	  fprintf(stderr, "TLS shutdown failed: %s\n",
		  gnutls_strerror(ret));
	  /* FIXME: Should we really call deinit? */
	}
    }
  else
    gnutls_deinit(data);    

#endif
  return OOP_CONTINUE;
}


void
isc_tls_destroy(struct isc_scb_internal* sci)
{
#ifdef HAVE_GNUTLS
  if(sci->tls_session)
    /* FIXME: We pass a pointer, this would probably break if 
     * gnutls_session_t changes (i.e. becomes a struct instead of a
     * pointer to a struct). That is unlikely, though.
     */
    sci->pub.master->event_source->on_time(sci->pub.master->event_source, 
					   OOP_TIME_NOW, 
					   isc_tls_die_callback,
					   sci->tls_session);   
#endif
}
